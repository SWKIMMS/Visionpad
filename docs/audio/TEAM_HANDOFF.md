# 사운드 통합 안내

## 이번 수정

- Windows의 CP949 환경에서도 설정·음성 파일을 UTF-8로 읽도록 정리했다.
- 음성 모델 폴더를 자동 생성하고, 파일 크기와 SHA-256을 확인해 손상된 다운로드를 다시 받는다.
- 다운로드가 완료된 파일만 적용하며, 인터넷 연결이 끊기면 재시도한다.
- 최신 팀 코드의 블루투스 SDK도 설치 과정에서 자동으로 준비한다.
- 일부 Python 버전에서 음성 오류 후 다음 안내가 대기하던 문제를 수정했다.
- 아이콘·마을 모듈과 음성 준비 도구도 설치 점검에 포함했다.
- 기존 효과음, 고정 영어 목소리 두 개, NPC 대화와 게임 규칙은 유지한다.

## 실행

프로젝트 전체를 받은 뒤 Windows는 `setup-windows.bat` → `game.bat`, Mac은 `setup-mac.command` → `start-mac.command` 순서로 실행한다. Python 3.12 64비트를 권장하며, 최초 설치에는 인터넷이 필요하다.

게임에서 **Test guide / Test Rowan**으로 목소리를 확인한다. **Speech volume**은 음성, **Sound volume**은 게임 소리다.

설치 오류와 점검 명령은 [SETUP.md](SETUP.md), 음원 출처는 [SOUND_MAP.md](SOUND_MAP.md)를 참고한다. 자동 설치·음성 검사는 GitHub Actions의 **Audio setup**에서 확인한다. 실제 헤드폰 청취와 패드 조작은 별도로 확인한다.
