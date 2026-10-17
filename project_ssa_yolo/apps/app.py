import logging  # 🛠️ 로그 필터링을 위해 logging 라이브러리 추가
import atexit
import hmac
import os
import threading
from pathlib import Path
from flask import Flask, jsonify
from flask_login import LoginManager
from flask import session, redirect, url_for, flash, request
from flask_wtf.csrf import CSRFProtect
from apps.config import config

# =================================================================
# 🛠️ [관제 허브 로그 폭발 완치] 3초마다 들어오는 labels_feed 로그만 콘솔에서 숨기기
# =================================================================
class NoLabelsFilter(logging.Filter):
    def filter(self, record):
        # 웹 서버 엔진 로그 메시지 중 'labels_feed'가 들어가 있으면 화면 출력을 차단합니다.
        return "labels_feed" not in record.getMessage()

# Flask가 사용하는 기본 웹 로거(werkzeug)를 강제로 가져와 필터 적용
flask_log = logging.getLogger('werkzeug')
flask_log.addFilter(NoLabelsFilter())
# =================================================================

csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "employee.signup"
login_manager.login_message = ""


def _shutdown_optional_services():
    """Stop non-detector background workers without preventing process exit."""
    try:
        from apps.services.starter import stop_services
        stop_services()
    except Exception as error:
        print(f"[shutdown] background service stop failed: {error}")


atexit.register(_shutdown_optional_services)

def create_app(config_key):
    app = Flask(__name__)
    selected_config = config[config_key]
    app.config.from_object(selected_config)
    local_database_enabled = app.config["LOCAL_DATABASE_ENABLED"]
    if local_database_enabled:
        # Only the explicitly selected legacy/test UI needs a local database.
        app.config["SQLALCHEMY_DATABASE_URI"] = selected_config.database_uri()

    # Werkzeug's debug reloader creates a parent and a serving child process.
    # Defer USB workers until a real request, which only the serving process
    # receives, so the reloader parent cannot contend for COM6.
    services_start_lock = threading.Lock()
    services_started = False
    services_initializing = False

    def ensure_services_started():
        nonlocal services_started
        with services_start_lock:
            if services_started:
                return
            from apps.services.starter import start_services
            start_services()
            services_started = True

    def startup_status_payload():
        from apps.services.starter import get_startup_status
        from apps.services.yolo_detector import get_ai_runtime_status
        payload = get_startup_status()
        ai = get_ai_runtime_status()
        ready = services_started and ai["ready"]
        if not ai["ready"] or (not ready and payload["stage"] != "SERVICE_FAILED"):
            payload.update(stage=ai["stage"], progress=ai["progress"], label=ai["label"])
        payload.update(ready=ready, processReady=True, aiReady=ai["ready"], ai=ai)
        payload.update({
            "servicesStarted": services_started,
            "servicesInitializing": services_initializing,
        })
        return payload

    # The read-only health route and protected startup route share one snapshot.
    app.extensions["ssa_runtime_status"] = startup_status_payload

    def start_services_async():
        nonlocal services_initializing
        with services_start_lock:
            from apps.services.yolo_detector import get_ai_runtime_status
            if services_initializing or (services_started and get_ai_runtime_status()["ready"]):
                return False
            services_initializing = True

        from apps.services.starter import mark_startup_requested
        mark_startup_requested()

        def initialize():
            nonlocal services_initializing
            try:
                from apps.services.yolo_detector import initialize_ai_runtime
                initialize_ai_runtime()
                ensure_services_started()
            except Exception:
                from apps.services.starter import mark_startup_failed
                mark_startup_failed()
            finally:
                with services_start_lock:
                    services_initializing = False

        threading.Thread(target=initialize, name="ssa-runtime-services-init", daemon=True).start()
        return True

    @app.before_request
    def initialize_runtime_services():
        # Administrator diagnostics must be a true read-only status request.
        # In particular, the first /stream/health request must not start the
        # sensor poller (and therefore must not open COM6) merely to report it.
        if request.endpoint in {
            "runtime_index",
            "stream.health_status",
            "stream.shutdown_runtime",
            "runtime_startup_status",
            "runtime_initialize_services",
        }:
            return
        if not local_database_enabled and request.endpoint in {"stream.index", "esp32_yolov12.index"}:
            return
        ensure_services_started()
    
    csrf.init_app(app)
    if local_database_enabled:
        from flask_migrate import Migrate
        from apps.extensions import db
        db.init_app(app)
        Migrate(app, db)
        from apps.db_test import project_db
        login_manager.init_app(app)

        from apps.crud import views as crud_views
        app.register_blueprint(crud_views.crud, url_prefix="/crud")
        from apps.auth import views as auth_views
        app.register_blueprint(auth_views.auth, url_prefix="/auth")
        from apps.main import views as main_views
        app.register_blueprint(main_views.main)
        from apps.detect_data import views as dd_views
        app.register_blueprint(dd_views.dd, url_prefix="/detect")
        from apps.control_page import views as control_views
        app.register_blueprint(control_views.control_page, url_prefix="/control")
    else:
        @app.get("/")
        def runtime_index():
            return jsonify({"profile": "ai", "health": "/stream/health"})

    from apps.stream import views as stream_views
    app.register_blueprint(stream_views.stream, url_prefix="/stream")
    
    from apps.esp32 import views as esp32_views
    app.register_blueprint(esp32_views.esp32_yolov12, url_prefix="/esp32_yolov12")

    def control_token_is_valid():
        configured_token = os.getenv("SSA_FLASK_CONTROL_TOKEN", "")
        request_token = request.headers.get("X-SSA-Flask-Control-Token", "")
        return bool(configured_token) and hmac.compare_digest(configured_token, request_token)

    @app.route("/stream/admin/startup-status", methods=["GET"])
    @csrf.exempt
    def runtime_startup_status():
        if not control_token_is_valid():
            return jsonify({"status": "FAIL", "error": "unauthorized"}), 403
        return jsonify({"status": "SUCCESS", **startup_status_payload()})

    @app.route("/stream/admin/initialize", methods=["POST"])
    @csrf.exempt
    def runtime_initialize_services():
        if not control_token_is_valid():
            return jsonify({"status": "FAIL", "error": "unauthorized"}), 403
        start_services_async()
        return jsonify({"status": "SUCCESS", **startup_status_payload()})
    
    @app.before_request
    def check_access_control():
        if not local_database_enabled:
            return
        if request.blueprint in ['auth', 'main', 'esp32_yolov12', 'stream']:
            return
        
        # 1. 예외 경로 설정
        if 'video_feed' in request.path:
            return
        
        # 2. 권한 정책 정의
        ACCESS_POLICIES = {
            'crud': ['admin'],
            'control_page': ['admin', 'drone', 'monitoring', 'standby'],
            'stream': ['admin', 'monitoring']
        }
        
        # 3. 권한 체크 로직
        current_role = session.get('role')
        allowed_roles = ACCESS_POLICIES.get(request.blueprint)
        
        if allowed_roles and current_role not in allowed_roles:
            flash("접근 권한이 없습니다.")
            return redirect(request.referrer or url_for('main.index'))
            
    return app
