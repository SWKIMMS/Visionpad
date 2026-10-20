# 설치와 실행

프로젝트 전체 폴더와 Python 3.11 이상이 필요하다. 새로 설치한다면 **Python 3.12 64비트**를 권장한다. Windows에서는 Python 설치 시 PATH 추가를 선택한다.

| 환경 | 처음 한 번 | 이후 실행 | 접속 주소 |
|---|---|---|---|
| Windows | `setup-windows.bat` | `game.bat` | http://127.0.0.1:8003 |
| Mac | `setup-mac.command` | `start-mac.command` | http://127.0.0.1:8000 |

설치 파일은 프로젝트 전용 환경에 패키지·공식 블루투스 SDK·영어 목소리 두 개를 준비한다. 최초 설치에는 인터넷이 필요하며, 음성 모델은 약 121MB다. 별도 API 키는 필요 없다. 설치가 끊겼으면 같은 설치 파일을 다시 실행하면 된다. 정상 파일은 재사용하고, 누락되거나 손상된 파일은 다시 받는다.

실행창은 플레이하는 동안 열어 둔다. 브라우저에서 클릭하거나 키를 눌러 소리를 활성화한다. **Test guide / Test Rowan**으로 음성을 확인할 수 있다. 게임 진행은 F3를 길게 눌러 저장한다.

## 오류가 나면

- **cp949 / UnicodeDecodeError:** 최신 프로젝트 전체를 받은 뒤 설치 파일을 다시 실행한다. 설정과 음성 파일은 UTF-8로 읽으며 Windows 실행 파일도 UTF-8 모드를 사용한다.
- **Voice model missing / Missing or damaged / Bluetooth SDK unavailable:** 설치 파일을 다시 실행한다. `models/piper`는 자동 생성된다.
- **모듈이나 효과음 누락:** `web`, `tools`, 설정 파일을 포함한 전체 프로젝트를 받는다. `requirements.txt` 설치만으로는 음성 모델이 준비되지 않는다.
- **Mac 실행 파일을 열 수 없음:** 프로젝트 폴더의 터미널에서 `zsh setup-mac.command`, `zsh start-mac.command`를 실행한다.
- **포트 사용 중:** 이미 켜진 같은 게임은 재사용한다. 다른 프로그램이면 실행창 안내에 따라 다른 포트를 사용한다.

가상환경을 활성화한 뒤 다음 명령으로 점검할 수 있다.

```bash
python tools/check_setup.py --synthesize
python launch_game.py --port 8004 --prepare-demo
```

음성 모델, 블루투스 SDK, 생성 음성, 저장 파일과 가상환경은 Git에 포함하지 않는다. 모델과 SDK는 설치 파일로 준비한다. 원본 MP3 효과음 18개는 `web/audio`에 포함되어 있다. 카메라 추적은 별도 실행 환경이며 기본 게임·음성 설치와 구분한다.
