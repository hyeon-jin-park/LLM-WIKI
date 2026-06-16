# LLM WIKI

LLM WIKI는 Markdown, TXT, PDF 자료를 로컬에서 읽고 검토 가능한 Markdown Wiki 페이지로 바꾸는 작은 지식베이스 도구입니다. 빈 Wiki로 시작해도 되고, 직접 자료를 넣어 개인용 문서 저장소처럼 키워도 됩니다.

자료 저장, 초안 생성, Wiki 반영, 검증은 모두 로컬 파일과 MCP Tool을 통해 동작합니다. 선택적 Chat 기능은 사용자의 로컬 CLI가 있을 때만 읽기 전용 subprocess로 연결됩니다.

![LLM WIKI empty workspace](mvp.png)

Wiki가 렌더링된 화면 예시는 [demo/usage-example.png](demo/usage-example.png)에 있습니다. 예시 이미지는 실행 데이터로 사용되지 않습니다.

## 포함된 구성

- `AGENTS.md`, `RULES.md`: Agent가 Wiki를 다룰 때 지켜야 할 운영 규칙
- `skills/wiki-curator/`: 자료 정리, 초안 작성, 링크 추천, 검증을 위한 재사용 가능한 Skill
- `raw/`: 사용자가 추가한 원본 자료 저장소
- `wiki/`: 승인된 Markdown Wiki 페이지 저장소
- `schema/`: Wiki 페이지와 raw item 규약
- `tools/mcp_server.py`: Agent와 Viewer가 함께 사용할 수 있는 stdio MCP 서버
- `app/`: 브라우저에서 Wiki를 보고 자료를 추가하는 Viewer
- `demo/`: 실제 렌더링 화면 예시

## Repository 구조

```text
raw/                 # 사용자가 넣는 원본 자료. 기본 상태는 비어 있음
wiki/                # 승인된 Markdown Wiki 페이지. 기본 상태는 비어 있음
schema/              # Wiki 페이지와 raw item 규약
tools/               # stdio MCP 서버
src/                 # Wiki Tool, MCP client, 선택적 CLI chat 연동
app/                 # 브라우저 Wiki Viewer
skills/wiki-curator/ # 자료 정리, 초안, 링크, 검증을 위한 Skill
demo/                # 실행 화면 캡처
AGENTS.md            # Agent 운영 지침
RULES.md             # 보안, 출처, 승인, 검증 규칙
README.md            # 실행 및 사용 설명
```

기본 저장소의 `raw/`와 `wiki/`에는 `.gitkeep`만 들어 있습니다. 개인 자료나 미리 채워진 Wiki 페이지는 포함하지 않습니다.

## 빠른 시작

### 1. 설치 및 실행

필요 환경:

- Python 3.10 이상
- 인터넷 연결: 최초 실행 시 `pypdf` 설치에 필요

```bash
git clone <repository-url>
cd llm-wiki
python3 run.py
```

`run.py`는 다음 작업을 자동으로 처리합니다.

- `.venv` 생성
- `requirements.txt` 의존성 설치
- MCP 기반 로컬 서버 실행
- `8000`번 포트가 사용 중이면 다른 포트 선택
- 브라우저 열기

브라우저를 자동으로 열지 않으려면:

```bash
python3 run.py --no-open
```

자료 추가, 초안 생성, Wiki 저장은 Python 서버와 MCP subprocess만으로 동작합니다. Codex CLI는 선택적 Chat 탭에서만 사용됩니다.

### 2. 자료 추가

1. 화면 중앙의 **첫 자료 추가** 또는 상단의 **+ 자료 추가**를 누릅니다.
2. `.md`, `.txt`, 텍스트 기반 `.pdf` 중 하나를 선택합니다.
3. 페이지 유형을 고릅니다.
   - `note`
   - `concept`
   - `guide`
   - `reference`
   - `project`
   - `journal`
4. 제목과 태그를 확인합니다.
5. 자동 생성된 Markdown 초안과 저장 경로를 검토합니다.
6. 문제가 없으면 **승인하고 Wiki에 저장**을 누릅니다.

스캔 이미지 PDF는 텍스트가 추출되지 않을 수 있으므로 OCR 처리 후 넣어야 합니다.

### 3. 결과 확인

승인 후 다음 변화가 생깁니다.

```text
raw/inbox/      → 승인 전 원본 저장 위치
raw/processed/  → 승인 후 원본 이동 위치
wiki/           → 생성된 Markdown Wiki 페이지
```

Wiki 페이지에는 `raw_source`, `source_url`, `last_verified` 같은 메타데이터가 들어가며, `source_trace` Tool로 원본과 Wiki 페이지의 연결을 확인할 수 있습니다.

## Import Flow

자료는 바로 Wiki에 들어가지 않습니다. 먼저 초안을 만들고, 사용자가 확인한 뒤 저장합니다.

```text
사용자 자료
→ raw/inbox 저장
→ 텍스트 추출
→ Schema 기반 Wiki 초안 생성
→ 사용자 검토
→ 승인 후 wiki/*.md 저장
→ raw/processed 이동
→ source_trace 및 validate_wiki 실행
```

중요한 규칙:

- 초안 생성은 Wiki를 변경하지 않습니다.
- Wiki 저장은 사용자 승인 후에만 발생합니다.
- 저장 후에는 반드시 검증을 수행합니다.
- Agent는 출처가 없는 사실을 만들어 넣으면 안 됩니다.

## MCP Tool 목록

MCP 서버는 `tools/mcp_server.py`입니다. Viewer와 Agent는 이 서버를 통해 Wiki에 접근합니다.

직접 실행:

```bash
.venv/bin/python tools/mcp_server.py
```

MCP host 설정 예시는 `mcp-config.example.json`에 있습니다.

| Tool | 동작 |
| --- | --- |
| `list_pages` | 전체 Wiki 페이지와 메타데이터 목록을 반환합니다. |
| `search_wiki` | 제목, 본문, 태그, 메타데이터를 검색합니다. |
| `read_page` | 특정 Markdown Wiki 페이지 전체를 읽습니다. |
| `page_summary` | 페이지 요약, 핵심 포인트, 메타데이터를 반환합니다. |
| `suggest_links` | 관련 Wiki 페이지 링크를 추천합니다. |
| `list_raw_items` | 대기 중이거나 처리된 원본 자료를 조회합니다. |
| `store_raw_item` | base64로 전달된 MD, TXT, PDF 자료를 안전하게 저장합니다. |
| `read_raw_item` | 원본 자료에서 텍스트를 추출합니다. |
| `draft_page_from_raw` | Wiki를 변경하지 않고 Schema 기반 초안을 만듭니다. |
| `source_trace` | Wiki 페이지와 원본 자료의 연결을 추적합니다. |
| `validate_wiki` | 메타데이터, 필수 섹션, 출처, 링크, 중복 제목을 검사합니다. |
| `upsert_page` | 승인된 Markdown 페이지를 생성하거나 갱신합니다. |

## Agent 사용 예시

Agent에게는 다음처럼 요청할 수 있습니다.

```text
Use the Wiki Curator Skill and LLM WIKI MCP tools.
Import raw/inbox/my-notes.txt as a concept page.
Show the complete draft and target path first.
Do not publish until I approve it.
After publishing, run source_trace and validate_wiki.
```

운영 규칙은 `AGENTS.md`와 `RULES.md`에 정리되어 있습니다. `skills/wiki-curator/SKILL.md`는 자료를 읽고, 초안을 만들고, 링크를 추천하고, 검증하는 재사용 가능한 작업 절차입니다.

## 선택적 Chat 기능

오른쪽 패널에는 `Tools / Chat` 탭이 있습니다. Chat은 세 단계로 동작합니다.

- `codex` CLI가 있으면 Codex subprocess를 사용합니다.
- Codex가 없고 `ollama` CLI가 있으면 Ollama subprocess를 사용합니다.
- 둘 다 없으면 `local-mcp` 모드로 동작합니다.

`local-mcp`는 LLM이 아니라 규칙 기반 작업자입니다. 검색, 원본 목록 확인, 초안 생성, 관련 링크 삽입안, 정리안, 검증은 처리할 수 있지만 번역, 재작성, 자연스러운 설명 같은 작업은 흉내 내지 않습니다.

앱은 실행할 때 provider를 자동으로 감지합니다. 설치되어 있으면 별도 설정 없이 연결되고, 없으면 Chat 패널과 `--doctor` 명령에서 설치 안내를 보여줍니다. 설치 자체는 사용자 권한, 네트워크, 로그인 상태가 필요할 수 있어 자동으로 실행하지 않습니다.

```bash
python3 run.py --doctor
```

동작 방식:

1. 서버가 MCP 읽기 Tool로 현재 Wiki 근거를 검색합니다.
2. 선택된 페이지가 있으면 전체 Markdown 내용을 함께 전달합니다.
3. Codex 또는 Ollama가 있으면 읽기 전용 subprocess로 자연어 작업을 요청합니다.
4. LLM provider가 없으면 local-mcp가 가능한 작업만 수행하고, 번역/재작성 요청에는 필요한 provider를 안내합니다.

Ollama 모델은 기본적으로 `llama3.1`을 사용합니다. 다른 모델을 쓰려면 실행 전에 환경변수를 지정합니다.

```bash
LLM_WIKI_OLLAMA_MODEL=qwen2.5 python3 run.py
```

Chat은 Wiki 페이지를 직접 생성하거나 수정할 수 없습니다. 변경 요청은 자료 추가/초안 승인 흐름으로 안내합니다.

Codex나 Ollama가 없어도 Wiki Viewer, MCP Tool, 자료 투입 파이프라인은 정상 동작합니다.

## 검증

기본 실행 확인:

```bash
python3 run.py --check
```

전체 테스트:

```bash
.venv/bin/python -m unittest discover -s tests -p "test_*.py"
.venv/bin/python tests/mcp_smoke.py
```

빈 Wiki에서 기대되는 결과:

```text
0 pages, 12 MCP tools
validate_wiki: ok true
unit tests: OK
MCP smoke: validate_ok true
```

## Local Data

- 원본 자료와 Wiki 저장은 로컬에서 수행됩니다.
- 저장소에 개인 raw 자료를 넣지 않는 것을 권장합니다.
- 기본 `raw/`와 `wiki/`는 빈 폴더 구조만 제공합니다.
- `.env`, 개인 자료, cache, `.venv`, archive 폴더는 Git에서 제외합니다.
- `demo/usage-example.png`는 화면 예시이며 실행 데이터가 아닙니다.
