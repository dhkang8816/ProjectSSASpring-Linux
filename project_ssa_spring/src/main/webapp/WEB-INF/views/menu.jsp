<%@ page language="java" contentType="text/html; charset=UTF-8"
	pageEncoding="UTF-8"%>

<%@ taglib prefix="c" uri="jakarta.tags.core"%>

<c:set var="isAdmin" value="false" scope="page" />
<c:set var="hasUserRole" value="false" scope="page" />
<c:set var="hasGuestRole" value="false" scope="page" />
<c:if test="${not empty sessionScope.SPRING_SECURITY_CONTEXT}">
	<c:forEach var="auth" items="${sessionScope.SPRING_SECURITY_CONTEXT.authentication.authorities}">
		<c:if test="${auth.authority eq 'ROLE_ADMIN'}">
			<c:set var="isAdmin" value="true" scope="page" />
		</c:if>
		<c:if test="${auth.authority eq 'ROLE_USER'}">
			<c:set var="hasUserRole" value="true" scope="page" />
		</c:if>
		<c:if test="${auth.authority eq 'ROLE_GUEST'}">
			<c:set var="hasGuestRole" value="true" scope="page" />
		</c:if>
	</c:forEach>
</c:if>
<c:set var="isGuestOnly" value="${hasGuestRole and not hasUserRole and not isAdmin}" scope="page" />

<style>
#ssaSidebar .sidebar-flask-control {
	flex: 0 0 auto !important;
	width: 100% !important;
	margin-top: auto !important;
	padding: 10px 10px 0 !important;
	box-sizing: border-box !important;
	background: #0f172a !important;
}

button#sidebarFlaskToggleButton {
	display: flex !important;
	position: relative !important;
	overflow: hidden !important;
	align-items: center !important;
	justify-content: center !important;
	box-sizing: border-box !important;
	width: 100% !important;
	min-height: 36px !important;
	padding: 0 10px !important;
	margin: 0 !important;
	border: 1px solid #f59e0b !important;
	border-radius: 6px !important;
	background: rgba(245, 158, 11, .12) !important;
	color: #fcd34d !important;
	font-family: inherit !important;
	font-size: 13px !important;
	font-weight: 800 !important;
	line-height: 1 !important;
	-webkit-appearance: none !important;
	appearance: none !important;
	cursor: pointer !important;
	transition: background-color .16s ease, border-color .16s ease, opacity .16s ease !important;
}

#sidebarFlaskToggleButton .sidebar-flask-progress {
	position: absolute;
	inset: 0 auto 0 0;
	width: 100%;
	background: linear-gradient(90deg, rgba(14, 165, 233, .58), rgba(56, 189, 248, .24));
	transform: scaleX(0);
	transform-origin: left center;
	transition: transform .35s ease;
	pointer-events: none;
}

#sidebarFlaskToggleButton .sidebar-flask-label {
	position: relative;
	z-index: 1;
}

button#sidebarFlaskToggleButton.is-starting {
	border-color: #38bdf8 !important;
	background: rgba(14, 165, 233, .13) !important;
	color: #e0f2fe !important;
	opacity: 1 !important;
}

button#sidebarFlaskToggleButton.is-starting:disabled {
	opacity: 1 !important;
}

button#sidebarFlaskToggleButton.is-online {
	border-color: #16a34a !important;
	background: rgba(22, 163, 74, .14) !important;
	color: #86efac !important;
}

button#sidebarFlaskToggleButton.is-offline {
	border-color: #dc2626 !important;
	background: rgba(220, 38, 38, .12) !important;
	color: #fca5a5 !important;
}

button#sidebarFlaskToggleButton.is-error {
	border-color: #f59e0b !important;
	background: rgba(245, 158, 11, .12) !important;
	color: #fcd34d !important;
}

button#sidebarFlaskToggleButton:disabled {
	cursor: not-allowed !important;
	opacity: .54 !important;
}

#ssaSidebar .sidebar-flask-control + .sidebar-discord {
	margin-top: 0 !important;
}
</style>


<nav id="ssaSidebar" class="ssa-sidebar">

	<!-- ===================================================
	     MINI CONTROL
	     =================================================== -->
	<div class="mini-control-box">

		<!-- LIVE MONITOR + CLOCK -->
		<div class="mini-control-header-bar">

			<div class="mini-live-title"></div>
			<span id="sidebarClock" class="mini-date-clock"> ---- -- --
				--:--:-- </span>
		</div>


		<!-- MINI VIDEO -->
		<div class="mini-video-display stream-off" id="mini_videoBox">

			<img id="mini_droneVideo" class="mini-streaming-frame" alt="미니 관제 화면">


			<div class="mini-video-footer">

				<span class="mini-channel-title" id="mini_sourceTitle">
					DRONE1 </span>

			</div>

		</div>


		<!-- CHANNEL BUTTON -->
		<div class="mini-drone-buttons">

			<button type="button" class="btn-mini-tab active"
				data-channel="video_1" onclick="switchMiniChannel('video_1')">
				D1</button>


			<button type="button" class="btn-mini-tab" data-channel="video_2"
				onclick="switchMiniChannel('video_2')">D2</button>


			<button type="button" class="btn-mini-tab" data-channel="video_3"
				onclick="switchMiniChannel('video_3')">D3</button>


			<button type="button" class="btn-mini-tab" data-channel="esp32"
				onclick="switchMiniChannel('esp32')">D4</button>

		</div>

	</div>


	<!-- ===================================================
	     MENU LIST
	     =================================================== -->
	<ul class="sidebar-list">


		<!-- ADMIN -->
		<c:if test="${isAdmin}">
			<li>

			<div class="sidebar-admin-row">

				<span class="sidebar-admin-title"> 관리자 메뉴 </span>

			</div>


			<ul class="submenu">

				<li><a href="<c:url value='/workflow/list'/>"> 보고서 결재 관리 </a></li>

				<li><a href="<c:url value='/member/list'/>"> 직원 관리 </a></li>

				<li><a href="<c:url value='/loginlog/list'/>"> 로그인 이력 </a></li>

				<li><a href="<c:url value='/commoncode/list'/>"> 시스템 코드 </a></li>

				<li><a href="<c:url value='/admin/diagnostics'/>"> 진단페이지 </a></li>

				<li><a data-detail-popup data-popup-name="alertTemplateSettings"
					href="<c:url value='/admin/alert-templates?popup=true'/>"> 경보 문구 설정 </a></li>

			</ul>

			</li>
		</c:if>


		<c:if test="${not isGuestOnly}">
		<!-- REPORT -->
		<li><a href="javascript:void(0);"> 보고서 등록 </a>


			<ul class="submenu">

				<li><a href="<c:url value='/patrolreport/list'/>"> 업무일지 목록
				</a></li>

			</ul></li>


		<!-- DRONE -->
		<li><a href="javascript:void(0);"> 드론관리 </a>


			<ul class="submenu">

				<li><a href="<c:url value='/flighthistory/list'/>"> 비행 이력 </a>
				</li>

				<li><a href="<c:url value='/drone/list'/>"> 드론 관리 </a></li>

			</ul></li>


		</c:if>

		<!-- DANGER -->
		<li><a href="javascript:void(0);"> 이상관리 </a>


			<ul class="submenu">

				<li><a href="<c:url value='/alert/list'/>"> 경보 이력 </a></li>

				<li><a href="<c:url value='/detection/list'/>"> 탐지 이력 </a></li>

				<li><a href="<c:url value='/dangerlog/list'/>"> 이상객체 탐지 이력
				</a></li>

				<li><a href="<c:url value='/dashboard/main'/>"> 통계 대시보드 </a></li>

			</ul></li>


		<c:if test="${not isGuestOnly}">
		<!-- ANIMAL -->
		<li><a href="javascript:void(0);"> 동물관리 </a>


			<ul class="submenu">

				<li><a href="<c:url value='/animal/list'/>"> 유기동물 관리 </a></li>

				<li><a href="<c:url value='/danger/list'/>"> 이상객체 관리 </a></li>

			</ul></li>
		</c:if>

	</ul>

	<c:if test="${isAdmin}">
		<div class="sidebar-flask-control">
			<button id="sidebarFlaskToggleButton" type="button"
				class="sidebar-flask-toggle is-error" aria-live="polite" disabled>
				<span class="sidebar-flask-progress" aria-hidden="true"></span>
				<span class="sidebar-flask-label">● Flask 확인 중</span>
			</button>
		</div>
	</c:if>

	<div class="sidebar-discord">
		<a class="sidebar-discord-link" href="${discordInviteUrl}" target="_blank"
			rel="noopener noreferrer" title="디스코드 서버 열기">
			<i class="fa-brands fa-discord" aria-hidden="true"></i>
			<span>디스코드 열기</span>
		</a>
	</div>

</nav>


<script>
(function () {

	const contextPath =
		"${pageContext.request.contextPath}";

	const miniChannelStorageKey =
		"ssa.miniSidebar.channel";

	const miniChannelKeys = [
		"video_1",
		"video_2",
		"video_3",
		"esp32"
	];

	let miniChannelKey =
		"video_1";

	let miniStatusTimer = null;

	let sidebarClockTimer = null;


	function getSavedMiniChannel() {

		try {
			const savedChannel = sessionStorage.getItem(
				miniChannelStorageKey
			);

			return miniChannelKeys.includes(
				savedChannel
			) ? savedChannel : null;
		} catch (error) {
			return null;
		}

	}


	function saveMiniChannel(
		channelKey
	) {

		try {
			sessionStorage.setItem(
				miniChannelStorageKey,
				channelKey
			);
		} catch (error) {
			// The sidebar remains usable when browser storage is unavailable.
		}

	}


	/* =====================================================
	   CLOCK
	   ===================================================== */

	   function updateSidebarClock() {

			const clock =
				document.getElementById("sidebarClock");

			if (!clock) {
				return;
			}

			const now = new Date();

			const yyyy =
				now.getFullYear();

			const mm =
				String(
					now.getMonth() + 1
				).padStart(2, "0");

			const dd =
				String(
					now.getDate()
				).padStart(2, "0");

			const hh =
				String(
					now.getHours()
				).padStart(2, "0");

			const min =
				String(
					now.getMinutes()
				).padStart(2, "0");

			const ss =
				String(
					now.getSeconds()
				).padStart(2, "0");

			clock.textContent =
				yyyy
				+ "-"
				+ mm
				+ "-"
				+ dd
				+ " "
				+ hh
				+ ":"
				+ min
				+ ":"
				+ ss;
		}


	/* =====================================================
	   CHANNEL NAME
	   ===================================================== */

	function getChannelName(
		channelKey
	) {

		const names = {

			video_1: "DRONE1",

			video_2: "DRONE2",

			video_3: "DRONE3",

			esp32: "DRONE4"

		};


		return (
			names[channelKey]
			|| channelKey
		);

	}


	/* =====================================================
	   CHANGE CHANNEL
	   ===================================================== */

	window.switchMiniChannel =
		function (
			channelKey
		) {

			if (!miniChannelKeys.includes(channelKey)) {
				return;
			}

			if (
				miniChannelKey
				=== channelKey
			) {
				saveMiniChannel(
					channelKey
				);
				return;
			}


			miniChannelKey =
				channelKey;


			saveMiniChannel(
				channelKey
			);


			document
				.querySelectorAll(
					"#ssaSidebar .btn-mini-tab"
				)
				.forEach(
					function (
						button
					) {

						button.classList
							.toggle(
								"active",
								button.dataset.channel
								=== channelKey
							);

					}
				);


			const title =
				document.getElementById(
					"mini_sourceTitle"
				);


			if (title) {

				title.textContent =
					getChannelName(
						channelKey
					);

			}


			disconnectMiniStream();

			checkMiniStatus();

		};


	/* =====================================================
	   DISCONNECT STREAM
	   ===================================================== */

	function disconnectMiniStream() {

		const img =
			document.getElementById(
				"mini_droneVideo"
			);


		if (!img) {
			return;
		}


		img.onerror =
			null;


		img.removeAttribute(
			"src"
		);


		delete img.dataset.channel;
	}


	/* =====================================================
	   STREAM
	   ===================================================== */

	function setMiniStream(
		enabled
	) {

		const img =
			document.getElementById(
				"mini_droneVideo"
			);


		const box =
			document.getElementById(
				"mini_videoBox"
			);


		if (
			!img
			|| !box
		) {
			return;
		}


		img.classList.toggle(
			"is-esp32-source",
			miniChannelKey === "esp32"
		);


		box.classList.remove(
			"stream-error"
		);


		if (!enabled) {

			disconnectMiniStream();

			return;
		}


		if (
			img.dataset.channel
			=== miniChannelKey
			&& img.getAttribute(
				"src"
			)
		) {

			return;
		}


		const streamUrl =
			contextPath
			+ "/yolo/videoFeed/"
			+ encodeURIComponent(
				miniChannelKey
			);


		img.dataset.channel =
			miniChannelKey;


		img.onerror =
			function () {

				box.classList.add(
					"stream-error"
				);

			};


		img.src =
			streamUrl
			+ "?t="
			+ Date.now();
	}


	/* =====================================================
	   STATUS
	   ===================================================== */

	function checkMiniStatus() {

		fetch(
			contextPath
			+ "/yolo/detection/status",
			{
				method: "GET",
				cache: "no-store"
			}
		)
		.then(
			function (
				response
			) {

				if (!response.ok) {
					throw new Error(
						"status error"
					);
				}

				return response.json();
			}
		)
		.then(
			function (
				response
			) {

				const box =
					document.getElementById(
						"mini_videoBox"
					);


				if (!box) {
					return;
				}


				const sources =
					response
					&& response.sources;


				if (
					!sources
					|| !sources[
						miniChannelKey
					]
				) {

					box.classList.add(
						"stream-off"
					);

					setMiniStream(
						false
					);

					return;
				}


				const sourceStatus =
					sources[
						miniChannelKey
					];


				const enabled =
					!!sourceStatus.running;


				box.classList.toggle(
					"stream-off",
					!enabled
				);


				setMiniStream(
					enabled
				);

			}
		)
		.catch(
			function () {

				const box =
					document.getElementById(
						"mini_videoBox"
					);


				if (box) {

					box.classList.add(
						"stream-error"
					);

				}


				disconnectMiniStream();

			}
		);

	}


	/* =====================================================
	   DETAIL
	   ===================================================== */

	function bindMiniDetail() {

		const box =
			document.getElementById(
				"mini_videoBox"
			);


		if (!box) {
			return;
		}


		box.addEventListener(
			"click",
			function () {

				window.location.href =
					contextPath
					+ "/yolo/detail?channel="
					+ encodeURIComponent(
						miniChannelKey
					);

			}
		);

	}


	/* =====================================================
	   INIT
	   ===================================================== */

	function initMiniSidebar() {

		const savedChannel =
			getSavedMiniChannel();


		if (savedChannel) {
			window.switchMiniChannel(
				savedChannel
			);
		}

		updateSidebarClock();


		if (
			sidebarClockTimer
		) {

			clearInterval(
				sidebarClockTimer
			);

		}


		sidebarClockTimer =
			setInterval(
				updateSidebarClock,
				1000
			);


		bindMiniDetail();


		checkMiniStatus();


		if (
			miniStatusTimer
		) {

			clearInterval(
				miniStatusTimer
			);

		}


		miniStatusTimer =
			setInterval(
				checkMiniStatus,
				2000
			);

	}


	if (
		document.readyState
		=== "loading"
	) {

		document.addEventListener(
			"DOMContentLoaded",
			initMiniSidebar
		);

	} else {

		initMiniSidebar();

	}

})();
</script>

<script>
(function () {
	var flaskToggleButton = document.getElementById('sidebarFlaskToggleButton');
	if (!flaskToggleButton) {
		return;
	}

	var contextPath = '${pageContext.request.contextPath}';
	var flaskActionInProgress = false;
	var flaskLabel = flaskToggleButton.querySelector('.sidebar-flask-label');
	var flaskProgress = flaskToggleButton.querySelector('.sidebar-flask-progress');

	function setFlaskButtonContent(label, progress) {
		flaskLabel.textContent = label;
		flaskProgress.style.transform = 'scaleX(' + Math.max(0, Math.min(100, Number(progress) || 0)) / 100 + ')';
	}

	function renderFlaskRuntime(state) {
		if (state && state.startupInProgress) {
			renderFlaskStartup(state);
			return;
		}
		var online = !!(state && state.online);
		var aiReady = !!(state && state.aiReady);
		var action = online ? 'stop' : 'start';
		flaskToggleButton.className = 'sidebar-flask-toggle ' + (online ? (aiReady ? 'is-online' : 'is-error') : 'is-offline');
		setFlaskButtonContent(online ? (aiReady ? '● Flask ON · AI 준비' : '● Flask ON · AI 미준비') : '● Flask OFF', 0);
		flaskToggleButton.dataset.action = action;
		flaskToggleButton.title = online ? '클릭하여 Flask 서버 종료' : '클릭하여 Flask 서버 시작';
		if (online && !aiReady) {
			flaskToggleButton.title = (state.aiError || state.startupLabel || 'AI 준비 미확인') + ' · 클릭하여 Flask 서버 종료';
		}
		flaskToggleButton.setAttribute('aria-label', flaskToggleButton.title);
		flaskToggleButton.disabled = flaskActionInProgress
			|| !(state && (online ? state.canStop : state.canStart));
	}

	function renderFlaskStartup(state) {
		flaskToggleButton.className = 'sidebar-flask-toggle is-starting';
		setFlaskButtonContent('◌ ' + (state.startupLabel || 'Flask 시작 중'), state.startupProgress);
		flaskToggleButton.dataset.action = '';
		flaskToggleButton.title = state.startupLabel || 'Flask 시작 상태를 확인하고 있습니다.';
		flaskToggleButton.setAttribute('aria-label', flaskToggleButton.title);
		flaskToggleButton.disabled = true;
	}

	function renderFlaskRuntimeError() {
		flaskToggleButton.className = 'sidebar-flask-toggle is-error';
		setFlaskButtonContent('● Flask 연결 오류', 0);
		flaskToggleButton.dataset.action = '';
		flaskToggleButton.title = 'Flask 상태를 확인하지 못했습니다.';
		flaskToggleButton.setAttribute('aria-label', flaskToggleButton.title);
		flaskToggleButton.disabled = true;
	}

	function requestFlaskRuntime() {
		return fetch(contextPath + '/admin/diagnostics/flask', {
            cache: 'no-store',
			headers: { 'Accept': 'application/json' }
		}).then(function (response) {
			if (!response.ok) {
				throw new Error('HTTP ' + response.status);
			}
			return response.json();
		});
	}

	function refreshFlaskRuntime() {
		if (flaskActionInProgress) {
			return;
		}

		requestFlaskRuntime().then(renderFlaskRuntime).catch(renderFlaskRuntimeError);
	}

	function pollFlaskStartup(deadline) {
		requestFlaskRuntime().then(function (state) {
			if (state.startupInProgress) {
				renderFlaskStartup(state);
				if (Date.now() < deadline) {
					window.setTimeout(function () { pollFlaskStartup(deadline); }, 500);
					return;
				}
			}
			if (state.online) {
				flaskActionInProgress = false;
				renderFlaskRuntime(state);
				return;
			}
			if (state.startupStage === 'START_FAILED'
				|| state.startupStage === 'SERVICE_FAILED'
				|| state.startupStage === 'AI_FAILED'
				|| Date.now() >= deadline) {
				flaskActionInProgress = false;
				renderFlaskRuntime(state);
				return;
			}
			renderFlaskStartup(state);
			window.setTimeout(function () { pollFlaskStartup(deadline); }, 500);
		}).catch(function () {
			if (Date.now() >= deadline) {
				flaskActionInProgress = false;
				renderFlaskRuntimeError();
				return;
			}
			window.setTimeout(function () { pollFlaskStartup(deadline); }, 500);
		});
	}

	function controlFlask(action) {
		if (action === 'stop'
			&& !window.confirm('Flask 서버를 종료하시겠습니까? 진행 중인 영상 데이터 전송이 중단됩니다.')) {
			return;
		}

		flaskActionInProgress = true;
		flaskToggleButton.disabled = true;
		if (action === 'start') {
			renderFlaskStartup({ startupLabel: 'Flask 시작 요청 전송', startupProgress: 15 });
		} else {
			flaskToggleButton.className = 'sidebar-flask-toggle is-error';
			setFlaskButtonContent('● Flask 종료 중', 0);
		}

		fetch(contextPath + '/admin/diagnostics/flask/' + action, {
			method: 'POST',
			headers: { 'Accept': 'application/json' }
		}).then(function (response) {
			if (!response.ok) {
				throw new Error('HTTP ' + response.status);
			}
			return response.json();
		}).then(function (state) {
			if (action === 'start' && state.success) {
				renderFlaskStartup(state);
				pollFlaskStartup(Date.now() + 30000);
				return;
			}
			flaskActionInProgress = false;
			renderFlaskRuntime(state);
			window.setTimeout(refreshFlaskRuntime, 1200);
		}).catch(function () {
			flaskActionInProgress = false;
			renderFlaskRuntimeError();
		});
	}

	flaskToggleButton.addEventListener('click', function () {
		var action = flaskToggleButton.dataset.action;
		if (action === 'start' || action === 'stop') {
			controlFlask(action);
		}
	});

	refreshFlaskRuntime();
	window.setInterval(refreshFlaskRuntime, 3000);
}());
</script>
