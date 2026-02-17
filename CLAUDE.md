# AgenticWorkflow

Claude Code 기반의 에이전트 워크플로우 자동화 프로젝트.

## 최종 목표

이 코드베이스의 최종 목표는 두 단계로 구성된다:

1. **워크플로우 설계**: 복잡한 작업을 Research → Planning → Implementation 3단계 구조의 `workflow.md`로 설계한다. Sub-agents/Agent Teams/Hooks/Skills/MCP Servers를 조합한 구현 설계를 포함한다.
2. **워크플로우 실행**: 생성된 `workflow.md`를 기준 삼아, 그 안에 정의된 에이전트·스크립트·자동화 구성을 **실제로 구현**한다. 워크플로우 문서는 설계도이고, 최종 산출물은 그 설계도대로 작동하는 실제 시스템이다.

> 워크플로우를 만드는 것은 중간 산출물이다. **워크플로우에 기술된 내용이 실제로 동작하는 것**이 최종 목표다.

## 절대 기준

> 이 프로젝트의 모든 설계·구현·수정 의사결정에 적용되는 최상위 규칙이다.
> 아래의 모든 원칙, 가이드라인, 관례보다 상위에 있다.

### 절대 기준 1: 최종 결과물의 품질

> **속도, 토큰 비용, 작업량, 분량 제한은 완전히 무시한다.**
> 모든 의사결정의 유일한 기준은 **최종 결과물의 품질**이다.
> 단계를 줄여서 빠르게 만드는 것보다, 단계를 늘려서라도 품질을 높이는 방향을 선택한다.

### 절대 기준 2: 단일 파일 SOT + 계층적 메모리 구조

> **단일 파일 SOT(Single Source of Truth) + 계층적 메모리 구조 설계 아래서, 수십 개의 에이전트가 동시에 작동해도 데이터 불일치가 발생하지 않는다.**

설계 함의:
- **상태 관리**: 모든 공유 상태는 단일 파일에 집중. 분산 금지.
- **쓰기 권한**: SOT 파일 쓰기는 Orchestrator/Team Lead만. 나머지는 읽기 전용 + 산출물 파일 생성.
- **충돌 방지**: 병렬 에이전트가 동일 파일을 동시 수정하는 구조 금지.

### 절대 기준 3: 코드 변경 프로토콜 (Code Change Protocol)

> **코드를 작성·수정·추가·삭제하기 전에, 반드시 아래 3단계를 내부적으로 수행한다.**
> 이 프로토콜을 건너뛰는 것은 절대 기준 위반이다.
> 프로토콜은 항상 수행하되, 분석 깊이는 변경의 영향 범위에 비례한다.

**Step 1 — 의도 파악**:
- 변경 목적(버그 수정/기능 추가/리팩토링/성능)과 제약(호환성, 기술 스택)을 1-2문장으로 정의
- 경미한 변경(오타, 주석, 포맷팅)이면 "파급 효과 없음" 확인 후 즉시 실행 가능

**Step 2 — 영향 범위 분석 (Ripple Effect Analysis)**:
- 직접 의존 + 호출 관계 (caller/callee)
- 구조적 관계 (상속, 합성, 참조)
- 데이터 모델/스키마/타입 연쇄 변경
- 테스트, 설정, 문서, API 스펙
- 강결합·샷건 서저리 위험이 있으면 **반드시** 사전 고지 후 사용자와 협의

**Step 3 — 변경 설계 (Change Plan)**:
- 단계별 변경 순서 (어떤 파일/함수부터 → 의존성 전파 → 테스트/문서 정합)
- 결합도 감소 / 응집도 증가 기회가 보이면 함께 제안 (실행은 사용자 승인 후)

**비례성 규칙:**

| 변경 규모 | 적용 깊이 |
|----------|---------|
| 경미 (오타, 주석) | Step 1만 — 파급 효과 없음 확인 |
| 표준 (함수/로직 변경) | 전체 3단계 |
| 대규모 (아키텍처, API) | 전체 3단계 + 사전 사용자 승인 필수 |

**커뮤니케이션 규칙:**
- 불필요하게 장황한 이론 설명은 피하고, 실질적인 코드와 구체적 단계 위주로 설명한다.
- 중요한 설계 선택에는 간단한 이유를 덧붙인다.
- 모호한 부분이 있어도 작업을 회피하지 말고, "합리적인 가정"을 명시한 뒤 최선의 설계를 제안한다.

### 절대 기준 간 우선순위

> **절대 기준 1(품질)이 최상위이다. 절대 기준 2(SOT)와 절대 기준 3(CCP)은 품질을 보장하기 위한 동위 수단이다.**
> 어느 기준이든 절대 기준 1과 충돌하면 품질이 이긴다. SOT와 CCP 모두 품질을 제약하는 **목적**이 아니라, 품질을 보장하기 위한 **수단**이다.

---

## 프로젝트 구조

```
AgenticWorkflow/
├── CLAUDE.md                              ← 이 파일 (Claude Code 전용 지시서)
├── AGENTS.md                              ← 모든 AI 에이전트 공통 지시서 (Hub — 방법론 SOT)
├── GEMINI.md                              ← Gemini CLI 전용 지시서 (Spoke)
├── README.md                              ← 프로젝트 소개
├── AGENTICWORKFLOW-USER-MANUAL.md         ← 이 코드베이스 자체의 사용자 매뉴얼
├── AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md  ← 설계 철학 및 아키텍처 전체 조감도
├── COPYRIGHT.md                           ← 저작권
├── .github/
│   └── copilot-instructions.md            ← GitHub Copilot 전용 지시서 (Spoke)
├── .cursor/
│   └── rules/
│       └── agenticworkflow.mdc            ← Cursor 전용 지시서 (Spoke, alwaysApply)
├── .gemini/
│   └── settings.json                      ← Gemini CLI 설정 (AGENTS.md 추가 로드)
├── .aider.conf.yml                        ← Aider 설정 (AGENTS.md 자동 로드)
├── .claude/
│   ├── settings.json                      ← Hook 설정 (Setup + SessionEnd)
│   ├── agents/                             ← Sub-agent 정의
│   │   └── translator.md                  (영→한 번역 전문 에이전트 — glossary 기반 용어 일관성)
│   ├── commands/                           ← Slash Commands
│   │   ├── install.md                     (Setup Init 검증 결과 분석 — /install)
│   │   └── maintenance.md                 (Setup Maintenance 건강 검진 — /maintenance)
│   ├── hooks/scripts/                     ← Context Preservation System + Setup Hooks
│   │   ├── context_guard.py               (Global Hook 통합 디스패처 — 모든 Global Hook의 진입점)
│   │   ├── _context_lib.py                (공유 라이브러리 — 파싱, 생성, SOT 캡처, Smart Throttling, Autopilot 상태 읽기·검증, 절삭 상수 중앙화, sot_paths() 경로 통합, 다단계 전환 감지, 결정 품질 태그 정렬)
│   │   ├── save_context.py                (SessionEnd/PreCompact 저장 엔진)
│   │   ├── restore_context.py             (SessionStart 복원 — RLM 포인터)
│   │   ├── update_work_log.py             (PostToolUse 작업 로그 누적 — Edit|Write|Bash|Task|NotebookEdit|TeamCreate|SendMessage|TaskCreate|TaskUpdate 9개 도구 추적)
│   │   ├── generate_context_summary.py    (Stop 증분 스냅샷 + Knowledge Archive + E5 Guard + Autopilot Decision Log 안전망)
│   │   ├── setup_init.py                  (Setup Init — 인프라 건강 검증, --init 트리거)
│   │   └── setup_maintenance.py           (Setup Maintenance — 주기적 건강 검진, --maintenance 트리거)
│   ├── context-snapshots/                 ← 런타임 스냅샷 (gitignored)
│   │   ├── latest.md                      (최신 스냅샷)
│   │   ├── knowledge-index.jsonl          (세션 간 축적 인덱스 — RLM 프로그래밍적 탐색 대상)
│   │   └── sessions/                      (세션별 아카이브)
│   └── skills/
│       ├── workflow-generator/            ← 워크플로우 설계·생성 스킬
│       │   ├── SKILL.md
│       │   └── references/                (claude-code-patterns, workflow-template, document-analysis-guide, context-injection-patterns, autopilot-decision-template)
│       └── doctoral-writing/              ← 박사급 학술 글쓰기 스킬
│           ├── SKILL.md
│           └── references/                (clarity-checklist, common-issues, before-after-examples, discipline-guides, korean-quick-reference)
├── prompt/                                ← 프롬프트 자료
│   ├── crystalize-prompt.md               (프롬프트 압축 기법)
│   ├── distill-partner.md                 (에센스 추출 및 최적화 인터뷰)
│   └── crawling-skill-sample.md           (크롤링 스킬 샘플)
└── coding-resource/                       ← 이론적 기반 자료
    └── recursive language models.pdf      (장기기억 구현 이론)
```

## Context Preservation System

컨텍스트 토큰 초과·`/clear`·압축 시 작업 내역 상실을 방지하는 자동 저장·복원 시스템이다.

### 동작 원리

| Hook 이벤트 | 스크립트 | 동작 |
|------------|---------|------|
| **Setup** (`--init`) | `setup_init.py` | 세션 시작 전 인프라 건강 검증 (Python 버전, 스크립트 구문, 디렉터리, PyYAML) |
| **Setup** (`--maintenance`) | `setup_maintenance.py` | 주기적 건강 검진 (stale archives, knowledge-index 무결성, work_log 크기) |
| **SessionEnd** (`/clear`) | `save_context.py` | 전체 스냅샷 저장 + Knowledge Archive 아카이빙 |
| **PreCompact** | `save_context.py` | 컨텍스트 압축 전 스냅샷 저장 + Knowledge Archive 아카이빙 |
| **SessionStart** | `restore_context.py` | RLM 패턴: 포인터 + 요약 + 과거 세션 인덱스 포인터 출력 |
| **PostToolUse** | `update_work_log.py` | 9개 도구(Edit, Write, Bash, Task, NotebookEdit, TeamCreate, SendMessage, TaskCreate, TaskUpdate) 작업 로그 누적. 토큰 75% 초과 시 proactive 저장 |
| **Stop** | `generate_context_summary.py` | 매 응답 후 증분 스냅샷 + Knowledge Archive 아카이빙 (30초 throttling, 5KB growth threshold) + Autopilot Decision Log 안전망 |

### Claude의 활용 방법

- 세션 시작 시 `[CONTEXT RECOVERY]` 메시지가 표시되면, 안내된 경로의 파일을 **반드시 Read tool로 읽어** 이전 맥락을 복원한다.
- 스냅샷은 `.claude/context-snapshots/latest.md`에 저장된다.
- **Knowledge Archive**: `knowledge-index.jsonl`은 세션 간 축적되는 구조화된 인덱스이다. Stop hook과 SessionEnd/PreCompact 모두에서 기록된다. 각 엔트리에는 completion_summary(도구 성공/실패), git_summary(변경 상태), session_duration_entries(세션 길이), phase(세션 전체 단계), phase_flow(다단계 전환 흐름, 예: `research → implementation`), primary_language(주요 파일 확장자)가 포함된다. Grep tool로 프로그래밍적 탐색이 가능하다 (RLM 패턴).
- **Resume Protocol**: 스냅샷에 포함된 "복원 지시" 섹션은 수정/참조 파일 목록과 세션 정보를 결정론적으로 제공한다. `[CONTEXT RECOVERY]` 출력에는 완료 상태(도구 성공/실패)와 Git 변경 상태도 표시된다.
- Hook 스크립트는 SOT(`state.yaml`)를 **읽기 전용**으로만 접근한다 (절대 기준 2 준수). SOT 파일 경로는 `sot_paths()` 헬퍼로 중앙 관리되며, `SOT_FILENAMES` 상수(`state.yaml`, `state.yml`, `state.json`)에서 파생된다.
- **절삭 상수 중앙화**: `_context_lib.py`에 10개 절삭 상수(`EDIT_PREVIEW_CHARS=1000`, `ERROR_RESULT_CHARS=3000`, `MIN_OUTPUT_SIZE=100` 등)를 중앙 정의. Edit preview는 5줄×1000자로 편집 의도·맥락을 보존하고, 에러 메시지는 3000자로 stack trace 전체를 보존한다.
- **다단계 전환 감지**: `detect_phase_transitions()` 함수가 sliding window(20개 도구, 50% 오버랩)로 세션 내 단계 전환(research → planning → implementation 등)을 결정론적으로 감지한다. Knowledge Archive의 `phase_flow` 필드에 기록된다.
- **결정 품질 태그 정렬**: 스냅샷의 "주요 설계 결정" 섹션(IMMORTAL 우선순위)은 품질 태그 기반으로 정렬된다 — `[explicit]` > `[decision]` > `[rationale]` > `[intent]` 순으로 15개 슬롯을 채워, 일상적 의도 선언(`하겠습니다` 패턴)이 실제 설계 결정을 밀어내지 않는다.
- **Autopilot 런타임 강화**: Autopilot 활성 시 SessionStart가 실행 규칙을 컨텍스트에 주입하고, 스냅샷에 Autopilot 상태 섹션(IMMORTAL 우선순위)을 포함하며, Stop hook이 Decision Log 누락을 감지·보완한다. PostToolUse는 work_log에 autopilot_step 필드를 추가하여 단계 진행을 추적한다.

### Hook 설정 위치

- **Global** (`~/.claude/settings.json`): `context_guard.py` 통합 디스패처를 통해 4개 Hook 실행
  - Stop → `context_guard.py --mode=stop` → `generate_context_summary.py`
  - PostToolUse → `context_guard.py --mode=post-tool` → `update_work_log.py` (matcher: `Edit|Write|Bash|Task|NotebookEdit|TeamCreate|SendMessage|TaskCreate|TaskUpdate`)
  - PreCompact → `context_guard.py --mode=pre-compact` → `save_context.py --trigger precompact`
  - SessionStart → `context_guard.py --mode=restore` → `restore_context.py`
- **Project** (`.claude/settings.json`): SessionEnd + Setup 이벤트
  - SessionEnd → `save_context.py --trigger sessionend`
  - Setup (init) → `setup_init.py` — 인프라 건강 검증 (`claude --init`)
  - Setup (maintenance) → `setup_maintenance.py` — 주기적 건강 검진 (`claude --maintenance`)

> **Setup Hook의 context_guard.py 우회 근거**: Setup은 세션 시작 **전**에 실행되는 프로젝트 고유 인프라 검증이므로, Global 디스패처와 독립적으로 Project 설정에서 직접 실행한다. SOT에 접근하지 않는다.

## 스킬 사용 판별

| 사용자 요청 패턴 | 스킬 | 진입점 |
|----------------|------|--------|
| "워크플로우 만들어줘", "자동화 파이프라인 설계", "작업 흐름 정의" | `workflow-generator` | SKILL.md → 케이스 판별 |
| "논문 스타일로 써줘", "학술적 글쓰기", "논문 문장 다듬기" | `doctoral-writing` | SKILL.md → 맥락 파악 |

## 설계 원칙

1. **P1 — 정확도를 위한 데이터 정제**: AI에게 전달하기 전 Python 등으로 노이즈 제거. 전처리·후처리 명시.
2. **P2 — 전문성 기반 위임 구조**: 전문 에이전트에게 위임하여 품질 극대화. Orchestrator는 조율만.
3. **P3 — 이미지/리소스 정확성**: 정확한 다운로드 경로 명시. placeholder 누락 불가.
4. **P4 — 질문 설계 규칙**: 최대 4개 질문, 각 3개 선택지. 모호함 없으면 질문 없이 진행. Claude Code에서는 `AskUserQuestion` 도구로 구현. Slash Command가 사전 정의된 선택형 개입이라면, AskUserQuestion은 동적 질문이 필요한 상황에 사용.

## Autopilot Mode (Claude Code 구현)

워크플로우 실행 시 `(human)` 단계와 AskUserQuestion을 자동 승인하는 모드. 상세: `AGENTS.md §5.1`

### 활성화 패턴

| 사용자 명령 | 동작 |
|-----------|------|
| "autopilot 모드로 실행", "자동 모드로 워크플로우 실행", "전자동으로 실행" | SOT에 `autopilot.enabled: true` 설정 후 워크플로우 시작 |
| "autopilot 해제", "수동 모드로 전환" | SOT에 `autopilot.enabled: false` — 다음 `(human)` 단계부터 적용 |

### Checkpoint별 동작

| Checkpoint | Autopilot 동작 |
|-----------|---------------|
| `(human)` + Slash Command | 완전한 산출물 생성 → 품질 극대화 기본값으로 자동 승인 → 결정 로그 기록 |
| AskUserQuestion | 선택지 중 품질 극대화 옵션 자동 선택 → 결정 로그 기록 |
| `(hook)` exit code 2 | **변경 없음** — 그대로 차단, 피드백 전달, 재작업 |

### Anti-Skip Guard + Verification Gate (2계층 품질 보장)

Orchestrator는 `current_step`을 순차적으로만 증가. 각 단계 완료 시 2계층 검증을 통과해야 진행한다:

1. **Anti-Skip Guard** (결정론적) — 산출물 파일 존재 + 최소 크기(100 bytes). Hook 계층의 `validate_step_output()` 함수가 수행.
2. **Verification Gate** (의미론적) — 산출물이 `Verification` 기준을 100% 달성했는지 에이전트 자기 검증. 실패 시 해당 부분만 재실행(최대 2회). `verification-logs/step-N-verify.md`에 기록.

> `Verification` 필드가 없는 단계는 Anti-Skip Guard만으로 진행 (하위 호환). 상세: `AGENTS.md §5.3`

### 결정 로그

자동 승인된 결정은 `autopilot-logs/step-N-decision.md`에 기록: 단계, 옵션, 선택 근거(절대 기준 1 기반).
Decision Log 표준 템플릿: `references/autopilot-decision-template.md`

### 런타임 강화 메커니즘

Autopilot의 설계 의도를 런타임에서 강화하는 하이브리드(Hook + 프롬프트) 시스템:

| 계층 | 메커니즘 | 강화 내용 |
|------|---------|----------|
| **Hook** (결정론적) | `restore_context.py` — SessionStart | Autopilot 활성 시 6개 실행 규칙 + 이전 단계 산출물 검증 결과를 컨텍스트에 주입 |
| **Hook** (결정론적) | `generate_snapshot_md()` — 스냅샷 | Autopilot 상태 + Agent Team 상태 섹션을 IMMORTAL 우선순위로 보존 (세션 경계에서 유실 방지) |
| **Hook** (결정론적) | `generate_context_summary.py` — Stop | 자동 승인 패턴 감지 → Decision Log 누락 시 보완 생성 (안전망) |
| **Hook** (결정론적) | `update_work_log.py` — PostToolUse | `autopilot_step` 필드로 단계 진행 추적 (사후 분석 가능) |
| **프롬프트** (행동 유도) | Execution Checklist (아래) | 각 단계의 시작/실행/완료 시 필수 행동 명시 |

> Hook 계층은 SOT를 읽기 전용으로만 접근하며 (절대 기준 2 준수), 쓰기는 `context-snapshots/`와 `autopilot-logs/`에만 수행한다.

### Autopilot Execution Checklist (MANDATORY)

Autopilot 모드에서 워크플로우를 실행할 때, 각 단계마다 아래 체크리스트를 **반드시** 수행한다.

#### 각 단계 시작 전
- [ ] SOT `current_step` 확인
- [ ] 이전 단계 산출물 파일 존재 + 비어있지 않음 확인
- [ ] 이전 단계 산출물 경로가 SOT `outputs`에 기록 확인
- [ ] 해당 단계의 `Verification` 기준 읽기 — "100% 완료"의 정의를 먼저 인식 (AGENTS.md §5.3)

#### 단계 실행 중
- [ ] 단계의 모든 작업을 **완전히** 실행 (축약 금지 — 절대 기준 1)
- [ ] 산출물을 **완전한 품질**로 생성

#### 단계 완료 후 (Verification Gate — `Verification` 필드 있는 단계만)
- [ ] 산출물 파일을 디스크에 저장
- [ ] 산출물을 각 `Verification` 기준 대비 자기 검증
- [ ] 실패 기준 있으면:
  - [ ] 실패 원인·누락 식별
  - [ ] 해당 부분만 재실행 (전체 재작업 아님)
  - [ ] 재검증 (최대 2회 재시도, 초과 시 사용자 에스컬레이션)
- [ ] 모든 기준 PASS 확인
- [ ] `verification-logs/step-N-verify.md` 생성
- [ ] SOT `outputs`에 산출물 경로 기록
- [ ] SOT `current_step` +1 증가
- [ ] `(human)` 단계: `autopilot-logs/step-N-decision.md` 생성
- [ ] `(human)` 단계: SOT `auto_approved_steps`에 추가

#### `(team)` 단계 추가 체크리스트
- [ ] `TeamCreate` 직후 → SOT `active_team` 기록 (name, status, tasks_pending)
- [ ] 각 Teammate는 보고 전 자기 Task의 검증 기준 대비 자기 검증 수행 (L1 — AGENTS.md §5.3)
- [ ] 각 Teammate 완료 시 → Team Lead가 단계 검증 기준 대비 종합 검증 (L2)
- [ ] L2 FAIL 시 → SendMessage로 구체적 피드백 + 재실행 지시
- [ ] 각 Teammate 완료 시 → SOT `active_team.tasks_completed` + `completed_summaries` 갱신
- [ ] 모든 Task 완료 시 → SOT `outputs` 기록, `current_step` +1, `active_team.status` → `all_completed`
- [ ] `TeamDelete` 직후 → SOT `active_team` → `completed_teams` 이동
- [ ] Teammate 산출물에 판단 근거(Decision Rationale) + 교차 참조 단서(Cross-Reference Cues) 포함 확인

#### 단계 완료 후 (번역 — `Translation: @translator`인 단계만)
- [ ] `@translator` 서브에이전트 호출 (`translations/glossary.yaml` 참조 포함)
- [ ] 번역 파일(`*.ko.md`) 디스크에 존재 확인
- [ ] 번역 파일 비어있지 않음 확인
- [ ] SOT `outputs.step-N-ko`에 번역 경로 기록
- [ ] `translations/glossary.yaml` 갱신 확인

#### NEVER DO
- `current_step`을 2 이상 한 번에 증가 금지
- 산출물 없이 다음 단계 진행 금지
- "자동이니까 간략하게" 금지 — 절대 기준 1 위반
- `(hook)` exit code 2 차단 무시 금지
- `(team)` 단계에서 Teammate가 SOT를 직접 수정 금지 — Team Lead만 SOT 갱신
- 세션 복원 시 `active_team`을 빈 객체로 초기화 금지 — 기존 `completed_summaries` 보존 필수 (보존적 재개 프로토콜)
- Verification 기준 FAIL인 채로 다음 단계 진행 금지 — 최대 2회 재시도 후 사용자 에스컬레이션
- Verification 기준을 "모두 PASS"로 허위 기록 금지 — 각 기준에 구체적 Evidence 필수

## 언어 및 스타일 규칙

- **프레임워크 문서·사용자 대화**: 한국어
- **워크플로우 실행**: 영어 (AI 성능 극대화 — 절대 기준 1 근거)
- **최종 산출물**: 영어 원본 + 한국어 번역 쌍 (각 단계별 `@translator` 서브에이전트가 생성)
- **기술 용어**: 영어 유지 (e.g., SOT, Agent Team, Hooks)
- **시각화**: Mermaid 다이어그램 선호
- **깊이**: 간략 요약보다 포괄적·데이터 기반 서술 선호

### English-First 실행 원칙

워크플로우 **실행** 시 모든 에이전트(Sub-agent, Teammate)는 **영어로 작업**하고 **영어로 산출물을 생성**한다.

| 단계 | 언어 | 근거 |
|------|------|------|
| 워크플로우 설계 (workflow-generator) | 한국어 | 사용자와의 대화 |
| 워크플로우 실행 (에이전트 작업) | **영어** | AI 성능 극대화 |
| 산출물 번역 | 영어→한국어 | `@translator` 서브에이전트 |
| SOT 기록 | 언어 무관 (경로·숫자) | 구조적 데이터 |

### 번역 프로토콜 (워크플로우 실행 시)

1. 각 단계의 영어 산출물이 SOT `outputs.step-N`에 기록된 후
2. 워크플로우에 `Translation: @translator`로 표기된 단계에 한해
3. `@translator` 서브에이전트 호출 (`.claude/agents/translator.md`)
4. 번역 완료 후 SOT `outputs.step-N-ko`에 한국어 경로 기록
5. 용어 사전(`translations/glossary.yaml`)이 자동 유지됨 (RLM 외부 지속 상태)

> **번역 대상**: 텍스트 콘텐츠 산출물만 (`.md`, `.txt` 등). 코드(`.py`, `.js`), 데이터(`.json`, `.csv`), 설정(`.yaml` config) 파일은 번역하지 않는다.
> **SOT 호환성**: `step-N-ko` 키는 Anti-Skip Guard의 `.isdigit()` 가드에 의해 자동으로 건너뛰어진다 (Hook 코드 변경 없음).

## 스킬 개발 규칙

새로운 스킬을 만들거나 기존 스킬을 수정할 때:

1. **모든 절대 기준을 반드시 포함**한다 — 해당 도메인에 맞게 맥락화하여 적용 (코드 변경이 아닌 도메인의 경우 절대 기준 3은 N/A 가능).
2. **파일 간 역할 분담**을 명확히 한다 — SKILL.md(WHY), references/(WHAT/HOW/VERIFY).
3. **절대 기준 간 충돌 시나리오**를 구체적으로 명시한다 — 추상적 규칙이 아닌 실전 판단 기준.
4. 수정 후 반드시 **절대 기준 관점에서 성찰**한다 — 문구만 넣지 않고 기존 내용과 충돌 여부를 점검.
