# 업로드 저장소 운영 안내

이 문서는 후속 작업 안내입니다. 아래 운영 명령은 이번 코드 수정에서 실행하지 않았습니다.

## 경로와 호환성

- 설정 이름: `SSA_UPLOAD_ROOT`
- 적용 우선순위: JVM 시스템 속성(`-DSSA_UPLOAD_ROOT=...`) → 프로세스 환경변수 → OS 기본값
- Linux 기본값: `/var/lib/project-ssa/uploads`
- Windows 기본값: `C:\upload`
- 설정값은 해당 OS의 절대경로여야 합니다. Linux에서 `C:/upload` 또는 상대경로는 거부합니다.
- 하위 폴더: 직원 `member`, 동물 `animals`, 탐지 `detection`, 위험 `dangerlog`
- 직원 파일명 `UUID$$원본파일명`, 동물 파일명 `UUID.확장자`, DB 파일명 값과 이미지 URL은 유지합니다.
- 사진이 없거나 외부 저장소를 읽을 수 없으면 기존 외부 `noImage.jpg`, WAR 기본 이미지 순으로 조회합니다. 조회 요청은 디렉터리를 생성하거나 기본 이미지를 복사하지 않습니다.
- 경로 구분자가 포함된 파일명과 저장 폴더 밖을 가리키는 심볼릭 링크는 읽기·저장·삭제 대상에서 제외합니다. 기존 DB 값을 일괄 수정하지 않습니다.

## Linux 운영자가 준비할 설정

Tomcat 프로세스에 적용할 값은 다음과 같습니다. 일반 셸에서 `export`한 값은 이미 실행 중인 systemd 서비스에 자동 적용되지 않습니다. 기존 JVM 옵션에 잘못된 `-DSSA_UPLOAD_ROOT` 값이 있는지도 확인해야 합니다.

```text
SSA_UPLOAD_ROOT=/var/lib/project-ssa/uploads
```

현재 서비스 파일에 선언된 실행 계정은 `tomcat:tomcat`입니다. 실제 서비스 계정을 확인한 뒤, 관리 권한 셸에서 다음 디렉터리를 준비할 수 있습니다. 이 명령에는 서비스 설정 변경·배포·재시작이 포함되지 않습니다.

```bash
install -d -o tomcat -g tomcat -m 0750 /var/lib/project-ssa
install -d -o tomcat -g tomcat -m 2770 \
  /var/lib/project-ssa/uploads \
  /var/lib/project-ssa/uploads/member \
  /var/lib/project-ssa/uploads/animals \
  /var/lib/project-ssa/uploads/detection \
  /var/lib/project-ssa/uploads/dangerlog
```

스냅샷을 생성하는 별도 프로세스도 같은 물리 저장소와 같은 `SSA_UPLOAD_ROOT` 값을 사용해야 합니다. 두 프로세스의 공유 그룹 및 파일 읽기·쓰기 권한을 확인하십시오. 이번 수정에서는 Flask/YOLO 설정을 변경하지 않았습니다.

`SSA_UPLOAD_ROOT`는 기존 PDF 캐시 코드에서도 사용합니다. 기존 환경변수를 바꾸면 PDF 캐시 위치에도 영향을 줄 수 있으므로 현재 설정과 캐시 경로를 확인하십시오. PDF 관련 코드는 수정하지 않았습니다.

`web.xml`에 설정된 multipart 임시 저장소는 별개입니다. Tomcat의 웹 애플리케이션 임시 디렉터리에도 서비스 계정의 쓰기 권한이 필요합니다.

## 기존 이미지 복사 명령 제안

기존 `/opt/tomcat/C:/upload` 등은 변경하지 않았습니다. 새 루트로 바꾸면 과거 사진을 표시하려면 파일 복사가 필요할 수 있습니다. 아래 명령은 `rsync`가 설치된 서버에서 운영자가 검토 후 실행할 예시입니다. 다른 과거 저장 위치가 있으면 소스 경로를 실제 위치로 바꾸십시오.

먼저 복사 예정 목록만 확인합니다.

```bash
for category in member animals detection dangerlog; do
  source_dir="/opt/tomcat/C:/upload/$category/"
  if [ -d "$source_dir" ]; then
    rsync -rtv --no-links --ignore-existing --dry-run \
      --chown=tomcat:tomcat --chmod=D2770,F0660 \
      "$source_dir" "/var/lib/project-ssa/uploads/$category/"
  fi
done
```

검토 후 같은 명령에서 `--dry-run`만 제거하면 복사합니다. 원본 파일은 유지하고, 대상에 이미 있는 파일은 덮어쓰지 않습니다. 같은 파일명의 내용이 다른 경우에는 별도로 대조해야 합니다. `--delete`, `--remove-source-files`, `mv`는 사용하지 않습니다. 파일명과 대소문자, 한글·공백을 유지하십시오. PDF 캐시는 위 복사 대상에 포함하지 않았습니다.

## 검증

프로젝트 디렉터리에서 Maven 테스트와 WAR 패키징을 수행할 수 있습니다.

```bash
mvn test
mvn -DskipTests package
```

운영 반영 후에는 로그인과 일반 CRUD, 기존 직원 사진 조회, 직원 사진 신규 등록·교체·초기화, 동물 사진 업로드·등록·수정, 탐지·위험 스냅샷, 기본 이미지, 재시작 후 조회를 확인하십시오. 실제 Windows 실행 및 운영 Tomcat/Oracle 연동은 단위 테스트와 구분하여 확인해야 합니다.
