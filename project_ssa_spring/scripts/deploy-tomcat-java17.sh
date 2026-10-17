#!/usr/bin/env bash
# Default: validate staged artifacts. --apply requires an administrator.
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
app_name=project_ssa_spring-0.0.1-SNAPSHOT
war_file="$project_dir/target/$app_name.war"
ecj_file="$project_dir/target/tomcat-java17/ecj-3.35.0.jar"
tomcat_base=/var/lib/tomcat10
mode=${1:---check}

if [[ $# -gt 1 || ( "$mode" != --check && "$mode" != --apply ) ]]; then
    echo "Usage: bash scripts/deploy-tomcat-java17.sh [--check|--apply]" >&2
    exit 2
fi

python3 -B - "$project_dir" "$war_file" "$ecj_file" <<'PY'
from pathlib import Path
import struct
import sys
from zipfile import ZipFile

project, war_path, ecj_path = map(Path, sys.argv[1:])
settings = project / 'src/main/resources/com/spring/properties/jdbc.properties'
expected = 'WEB-INF/classes/com/spring/properties/jdbc.properties'
with ZipFile(war_path) as war:
    entries = [name for name in war.namelist() if name.endswith('jdbc.properties')]
    if entries != [expected] or war.read(expected) != settings.read_bytes():
        raise SystemExit('Invalid JDBC resource placement/content. Run mvn clean verify.')
    forbidden = ('servlet-api', 'jsp-api', 'jasper', 'ecj', 'eclipse-jdt')
    if any(name.startswith('WEB-INF/lib/') and any(part in name.rsplit('/', 1)[1]
           for part in forbidden) for name in war.namelist()):
        raise SystemExit('Container APIs/compiler must not be bundled in WEB-INF/lib.')
with ZipFile(ecj_path) as ecj:
    for name in ecj.namelist():
        if name.endswith('.class') and not name.startswith('META-INF/versions/'):
            major = struct.unpack('>H', ecj.read(name)[6:8])[0]
            if major > 61:
                raise SystemExit('ECJ contains classes that cannot run on Java 17.')
    ecj.getinfo('org/eclipse/jdt/internal/compiler/env/INameEnvironment.class')
print('WAR resource placement and Java 17 compiler: OK (no credentials displayed)')
PY

if [[ "$mode" == --check ]]; then
    echo "Validation only. No Tomcat files or services changed."
    exit 0
fi

if [[ $EUID -ne 0 ]]; then
    echo "Administrator required: sudo bash scripts/deploy-tomcat-java17.sh --apply" >&2
    exit 1
fi

# Abort rather than edit a custom class-loader configuration automatically.
python3 -B - "$tomcat_base/conf/catalina.properties" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
loader = next((line.split('=', 1)[1] for line in text.splitlines()
               if line.startswith('common.loader=')), '')
base = loader.find('${catalina.base}/lib/*.jar')
home = loader.find('${catalina.home}/lib')
if base < 0 or home < 0 or base >= home:
    raise SystemExit('Review common.loader: CATALINA_BASE/lib must precede CATALINA_HOME/lib.')
PY

for existing in "$tomcat_base"/lib/*.jar; do
    [[ -e "$existing" ]] || continue
    case "${existing##*/}" in
        ecj-3.35.0.jar) ;;
        *ecj*|*jdt*)
            echo "Review the existing compiler before deployment: $existing" >&2
            exit 1 ;;
    esac
done

backup_dir=$(mktemp -d /var/backups/project-ssa-java17.XXXXXXXX)
chmod 0700 "$backup_dir"
if [[ -f "$tomcat_base/webapps/$app_name.war" ]]; then
    cp -a -- "$tomcat_base/webapps/$app_name.war" "$backup_dir/original.war"
fi
if [[ -d "$tomcat_base/webapps/$app_name" ]]; then
    tar -czf "$backup_dir/exploded-webapp.tar.gz" -C "$tomcat_base/webapps" "$app_name"
fi
if [[ -f "$tomcat_base/lib/ecj-3.35.0.jar" ]]; then
    cp -a -- "$tomcat_base/lib/ecj-3.35.0.jar" "$backup_dir/original-ecj.jar"
fi
echo "Backup: $backup_dir"

trap 'result=$?; trap - ERR; echo "Deployment failed; backup retained at $backup_dir. Attempting to start Tomcat." >&2; systemctl start tomcat10 || true; exit "$result"' ERR
systemctl stop tomcat10
install -o root -g root -m 0644 "$ecj_file" "$tomcat_base/lib/ecj-3.35.0.jar"
install -o root -g tomcat -m 0640 "$war_file" "$tomcat_base/webapps/$app_name.war.new"
mv -f -- "$tomcat_base/webapps/$app_name.war.new" "$tomcat_base/webapps/$app_name.war"
systemctl start tomcat10
trap - ERR
echo "Tomcat start requested. Verify HTTP and new logs; no system JAR was removed."
