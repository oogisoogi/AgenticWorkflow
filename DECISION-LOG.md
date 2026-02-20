# AgenticWorkflow Decision Log (ADR)

이 문서는 AgenticWorkflow 프로젝트의 **모든 주요 설계 결정**을 시간순으로 기록한다.
각 결정은 ADR(Architecture Decision Record) 형식을 따르며, 맥락·결정·근거·대안·상태를 포함한다.

> **목적**: 프로젝트의 "왜?"를 추적하여, 미래의 의사결정자(사람 또는 AI)가 기존 결정의 맥락을 이해하고 일관된 판단을 내릴 수 있게 한다.

---

## ADR 형식

```
### ADR-NNN: 제목
- **날짜**: YYYY-MM-DD (커밋 기준)
- **상태**: Accepted / Superseded / Deprecated
- **맥락**: 결정이 필요했던 상황
- **결정**: 선택한 방향
- **근거**: 선택의 이유
- **대안**: 검토했으나 선택하지 않은 방향
- **관련 커밋**: 해시 + 메시지
```

---

## 1. Foundation (프로젝트 기반)

### ADR-001: 워크플로우는 중간물, 동작하는 시스템이 최종 산출물

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: 많은 자동화 프로젝트가 "계획을 세우는 것"에서 멈춘다. workflow.md를 만드는 것 자체가 목표가 되는 함정을 방지해야 했다.
- **결정**: 프로젝트를 2단계로 구분한다 — Phase 1(workflow.md 설계 = 중간 산출물), Phase 2(에이전트·스크립트·자동화가 실제 동작 = 최종 산출물).
- **근거**: 설계도가 아무리 정교해도 실행되지 않으면 미완성이다. Phase 2가 없는 Phase 1은 가치의 절반만 달성한다.
- **대안**: workflow.md 자체를 최종 산출물로 취급 → 기각 (실행 가능성 검증 불가)
- **관련 커밋**: `348601e` Initial commit: AgenticWorkflow project

### ADR-002: 절대 기준 체계 — 3개 기준의 계층적 우선순위

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: 프로젝트에 여러 설계 원칙이 존재하는데, 원칙 간 충돌 시 판단 기준이 필요했다. "빠르게 할지 vs 품질을 높일지", "SOT 단순성 vs 기능 확장" 등의 트레이드오프가 반복되었다.
- **결정**: 3개 절대 기준을 정의하고, 명시적 우선순위를 설정한다:
  1. **절대 기준 1 (품질)** — 최상위. 모든 기준의 존재 이유.
  2. **절대 기준 2 (SOT)** — 데이터 무결성 보장 수단. 품질에 종속.
  3. **절대 기준 3 (CCP)** — 코드 변경 품질 보장 수단. 품질에 종속.
- **근거**: 추상적인 "모든 원칙이 중요하다"는 실전에서 작동하지 않는다. 명시적 우선순위가 있어야 충돌 시 결정론적으로 해소할 수 있다.
- **대안**:
  - 모든 원칙을 동위 → 기각 (충돌 해소 기준 부재)
  - SOT를 최상위 → 기각 (데이터 무결성이 목적이 아닌 수단)
- **관련 커밋**: `348601e` Initial commit

### ADR-003: 품질 절대주의 — 속도·비용·분량 완전 무시

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: AI 기반 자동화에서 토큰 비용, 실행 시간, 에이전트 수를 최소화하려는 경향이 있다. 이로 인해 단계를 생략하거나, 산출물을 축약하거나, 검증을 건너뛰는 안티패턴이 발생한다.
- **결정**: "속도, 토큰 비용, 작업량, 분량 제한은 **완전히 무시**한다. 유일한 의사결정 기준은 최종 결과물의 품질이다."
- **근거**: 비용 절감으로 품질이 떨어지면, 결국 재작업 비용이 더 크다. 처음부터 최고 품질을 목표로 하는 것이 장기적으로 효율적이다.
- **대안**: 비용-품질 트레이드오프 매트릭스 → 기각 (판단 복잡도 증가, 항상 비용 쪽으로 기울어지는 인센티브 구조)
- **관련 커밋**: `348601e` Initial commit

### ADR-004: Research → Planning → Implementation 3단계 구조적 제약

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: 워크플로우의 단계 수와 구조를 자유롭게 정할 수 있으면, 에이전트가 Research를 건너뛰거나 Planning 없이 구현에 들어가는 문제가 발생한다.
- **결정**: 모든 워크플로우는 반드시 3단계(Research → Planning → Implementation)를 따른다. 이것은 관례가 아닌 구조적 제약이다.
- **근거**:
  - Research 생략 → 불충분한 정보로 작업 → 품질 하락 (절대 기준 1 위반)
  - Planning 생략 → 사람 검토 없이 구현 → 방향 오류 누적
  - Implementation 생략 → 설계도만 존재하는 미완성 시스템 (ADR-001 위반)
- **대안**: 유연한 N단계 → 기각 (구조적 보장 없음)
- **관련 커밋**: `348601e` Initial commit

### ADR-005: 설계 원칙 P1-P4 — 절대 기준의 하위 원칙

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: 절대 기준은 "무엇을 최적화하는가"를 정의하지만, "어떻게"에 대한 구체적 지침이 필요했다.
- **결정**: 4개 설계 원칙을 정의한다:
  - **P1**: 정확도를 위한 데이터 정제 (Code가 정제, AI가 판단)
  - **P2**: 전문성 기반 위임 구조 (Orchestrator는 조율만)
  - **P3**: 리소스 정확성 (placeholder 누락 불가)
  - **P4**: 질문 설계 규칙 (최대 4개, 각 3개 선택지)
- **근거**: P1은 RLM 논문의 Code-based Filtering, P2는 재귀적 Sub-call과 대응. P3은 실행 가능성 보장, P4는 사용자 피로 최소화.
- **대안**: 원칙 없이 절대 기준만으로 운영 → 기각 (너무 추상적)
- **관련 커밋**: `348601e` Initial commit

### ADR-006: 단일 파일 SOT 패턴

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: 수십 개의 에이전트가 동시에 작동하는 환경에서, 상태를 여러 파일에 분산하면 데이터 불일치가 불가피하다.
- **결정**: 모든 공유 상태는 단일 파일(`state.yaml`)에 집중한다. 쓰기 권한은 Orchestrator/Team Lead만 보유하고, 나머지 에이전트는 읽기 전용 + 산출물 파일 생성만 한다.
- **근거**: 단일 쓰기 지점 패턴은 분산 시스템의 데이터 일관성을 보장하는 검증된 패턴이다. 복수 에이전트의 동시 수정으로 인한 충돌을 원천 차단한다.
- **대안**:
  - 분산 상태 + 병합 전략 → 기각 (복잡도 폭발, 충돌 해소 오버헤드)
  - 데이터베이스 기반 → 기각 (외부 의존성, 오버엔지니어링)
- **관련 커밋**: `348601e` Initial commit

### ADR-007: 코드 변경 프로토콜 (CCP) + 비례성 규칙

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: 코드 변경 시 파급 효과를 분석하지 않으면, 한 곳의 수정이 예상치 못한 곳에서 에러를 발생시킨다 (샷건 서저리).
- **결정**: 코드 변경 전 반드시 3단계(의도 파악 → 영향 범위 분석 → 변경 설계)를 수행한다. 단, 비례성 규칙으로 변경 규모에 따라 분석 깊이를 조절한다:
  - 경미(오타, 주석) → Step 1만
  - 표준(함수/로직 변경) → 전체 3단계
  - 대규모(아키텍처, API) → 전체 3단계 + 사전 사용자 승인
- **근거**: 프로토콜 자체를 건너뛰지는 않되, 사소한 변경에 과도한 분석은 절대 기준 1(품질) 위반이다. 비례성 규칙으로 프로토콜의 존재와 실용성을 동시에 보장한다.
- **대안**: 모든 변경에 동일한 깊이 적용 → 기각 (오타 수정에 풀 분석은 비생산적)
- **관련 커밋**: `348601e` Initial commit

---

## 2. Documentation Architecture (문서 아키텍처)

### ADR-008: Hub-and-Spoke 문서 구조 — AGENTS.md를 Hub으로

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: 여러 AI 도구(Claude Code, Cursor, Copilot, Gemini)가 각자의 설정 파일을 갖는데, 공통 규칙을 각 파일에 중복 작성하면 동기화 문제가 발생한다.
- **결정**: Hub-and-Spoke 패턴을 채택한다:
  - **Hub**: `AGENTS.md` — 모든 AI 에이전트 공통 규칙 (방법론 SOT)
  - **Spoke**: `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.cursor/rules/agenticworkflow.mdc` — 각 도구별 구현 상세
- **근거**: 공통 규칙의 단일 정의 지점(AGENTS.md)을 유지하면서, 도구별 특수 사항(Hook 설정, Slash Command 등)은 각 Spoke에서 다룬다. 이는 절대 기준 2(SOT)의 문서 차원 적용이다.
- **대안**:
  - 단일 통합 문서 → 기각 (도구별 특수 사항 포함 시 비대해짐)
  - 완전 독립 문서 → 기각 (공통 규칙 중복, 동기화 불가)
- **관련 커밋**: `5b649cb` feat: Hub-and-Spoke universal system prompt for all AI CLI tools

### ADR-009: RLM 논문을 이론적 기반으로 채택

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: 에이전트 아키텍처의 설계 배경이 필요했다. "왜 SOT를 외부 파일로 관리하는가", "왜 Python으로 전처리하는가"에 대한 이론적 근거가 필요했다.
- **결정**: MIT CSAIL의 Recursive Language Models (RLM) 논문을 이론적 기반으로 채택한다. RLM의 핵심 패러다임 — "프롬프트를 신경망에 직접 넣지 말고, 외부 환경의 객체로 취급하라" — 이 AgenticWorkflow의 설계 전반에 적용된다.
- **근거**: RLM의 Python REPL ↔ SOT, 재귀적 Sub-call ↔ Sub-agent 위임, Code-based Filtering ↔ P1 원칙 등 구조적 대응이 정확하다. 이론적 뿌리가 있으면 설계 일관성을 유지하기 쉽다.
- **대안**: 독자적 프레임워크 → 기각 (이론적 검증 부재)
- **관련 커밋**: `e051837` docs: Add coding-resource PDF

### ADR-010: 독립 아키텍처 문서 분리

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: CLAUDE.md(무엇이 있는가), AGENTS.md(어떤 규칙인가), USER-MANUAL(어떻게 쓰는가)은 있지만, "왜 이렇게 설계했는가"를 체계적으로 서술하는 문서가 없었다.
- **결정**: `AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md`를 별도 문서로 생성한다. 설계 철학, 아키텍처 조감도, 구성 요소 관계, 설계 원칙의 이론적 배경을 서술한다.
- **근거**: "WHY" 문서가 없으면, 시간이 지남에 따라 설계 결정의 맥락이 유실되고, 상충하는 수정이 발생한다.
- **대안**: CLAUDE.md에 통합 → 기각 (프롬프트 크기 증가, 도구별 지시서와 철학 문서의 성격 차이)
- **관련 커밋**: `feba502` docs: Add architecture and philosophy document

### ADR-011: Spoke 파일 정리 — 사용하지 않는 도구 제거

- **날짜**: 2026-02-20
- **상태**: Accepted
- **맥락**: 초기에 Amazon Q, Windsurf, Aider 등 다양한 AI 도구용 Spoke 파일을 만들었지만, 실제로 사용하지 않는 도구의 설정 파일이 유지보수 부담이 되었다.
- **결정**:
  - `.amazonq/`, `.windsurf/` 삭제 및 모든 문서에서 참조 제거
  - `.aider.conf.yml` 삭제 및 참조 제거
  - `.github/copilot-instructions.md`는 삭제 후 복원 (실제 사용 중)
- **근거**: 사용하지 않는 파일은 동기화 대상만 늘리고 품질에 기여하지 않는다. 필요할 때 다시 만들면 된다.
- **대안**: 모든 Spoke 유지 → 기각 (문서 동기화 시 불필요한 작업량 증가)
- **관련 커밋**: `162a322`, `a4afb26`, `708cb57` (복원), `5634b0e`

---

## 3. Context Preservation System (컨텍스트 보존)

### ADR-012: Hook 기반 컨텍스트 자동 보존 시스템

- **날짜**: 2026-02-16
- **상태**: Accepted
- **맥락**: Claude Code의 컨텍스트 윈도우가 소진되면(`/clear`, 압축), 진행 중이던 작업 맥락이 완전히 상실된다. 수동 저장은 까먹기 쉽고, 일관성이 없다.
- **결정**: 5개 Hook 이벤트(SessionStart, PostToolUse, Stop, PreCompact, SessionEnd)에 Python 스크립트를 연결하여 자동 저장·복원 시스템을 구축한다. RLM 패턴(외부 메모리 객체 + 포인터 기반 복원)을 적용한다.
- **근거**: 자동화된 보존은 사용자 개입 없이 100% 작동한다. RLM 패턴을 적용하면 전체 내역을 주입하는 대신, 포인터+요약으로 필요한 부분만 로드할 수 있다.
- **대안**:
  - 수동 저장 (`/save` 커맨드) → 기각 (까먹기 쉬움)
  - 전체 트랜스크립트 백업 → 기각 (크기 문제, 컨텍스트 윈도우에 못 넣음)
- **관련 커밋**: `bb7b9a1` feat: Add Context Preservation Hook System

### ADR-013: Knowledge Archive — 세션 간 축적 인덱스

- **날짜**: 2026-02-17
- **상태**: Accepted
- **맥락**: 단일 세션의 스냅샷만으로는 프로젝트의 장기적 이력을 추적할 수 없다. "이전에 비슷한 에러를 어떻게 해결했는가?" 같은 cross-session 질문에 답할 수 없었다.
- **결정**: `knowledge-index.jsonl`에 세션별 메타데이터를 구조화하여 축적한다. Grep으로 프로그래밍적 탐색이 가능한 형태로 설계한다 (RLM sub-call 대응).
- **근거**: JSONL 형식은 append-only로 동시성 문제가 적고, Grep/jq로 프로그래밍적 탐색이 가능하다. 이는 RLM의 "외부 환경 탐색" 패턴과 일치한다.
- **대안**:
  - SQLite → 기각 (외부 의존성, 텍스트 도구로 탐색 불가)
  - 단순 MD 파일 목록 → 기각 (구조화된 메타데이터 검색 불가)
- **관련 커밋**: `d1acb9f` feat: RLM long-term memory + context quality optimization

### ADR-014: Smart Throttling — 30초 + 5KB 임계값

- **날짜**: 2026-02-17
- **상태**: Accepted
- **맥락**: Stop hook이 매 응답마다 실행되면, 짧은 응답에서도 불필요한 스냅샷이 반복 생성되어 성능에 영향을 준다.
- **결정**: Stop hook에 30초 dedup window + 5KB growth threshold를 적용한다. SessionEnd/PreCompact는 5초 window, SessionEnd는 dedup 면제 (마지막 기회 보장).
- **근거**: 30초 내 변화가 없으면 동일 내용의 스냅샷 재생성은 낭비다. 5KB 성장 임계값은 의미 있는 변화가 있을 때만 갱신하도록 보장한다.
- **대안**: 항상 저장 → 기각 (성능 부담), 시간만 체크 → 기각 (변화 없는 저장 발생)
- **관련 커밋**: `7363cc4` feat: Context memory quality optimization — throttling, archive, restore

### ADR-015: IMMORTAL-aware 압축 + 감사 추적

- **날짜**: 2026-02-19
- **상태**: Accepted
- **맥락**: 스냅샷이 크기 한계를 초과할 때, 단순 절삭(truncation)을 하면 핵심 맥락(현재 작업, 설계 결정, Autopilot/ULW 상태)이 유실될 수 있다.
- **결정**: `<!-- IMMORTAL -->` 마커가 있는 섹션을 우선 보존하고, 비-IMMORTAL 콘텐츠를 먼저 절삭한다. 압축 각 Phase(1~7)가 제거한 문자 수를 HTML 주석으로 기록한다 (감사 추적).
- **근거**: "현재 작업"과 "설계 결정"은 세션 복원의 핵심이다. 이것이 유실되면 복원 품질이 급락한다. 감사 추적은 압축 동작의 디버깅을 가능하게 한다.
- **대안**: 균등 절삭 → 기각 (핵심 맥락 유실 위험), 우선순위 없는 FIFO → 기각 (최근 맥락만 보존, 오래된 핵심 결정 유실)
- **관련 커밋**: `2c91985` feat: Context Preservation 품질 강화 — 18항목 감사·성찰 구현

### ADR-016: E5 Empty Snapshot Guard — 다중 신호 감지

- **날짜**: 2026-02-20
- **상태**: Accepted
- **맥락**: tool_use가 0인 빈 스냅샷이 기존의 풍부한 `latest.md`를 덮어쓰는 문제가 발생했다. 단순 크기 비교로는 "작지만 의미 있는" 스냅샷을 정확히 구분할 수 없었다.
- **결정**: 다중 신호 감지(크기 ≥ 3KB OR ≥ 2개 섹션 마커)로 "풍부한 스냅샷"을 정의하고, `is_rich_snapshot()` + `update_latest_with_guard()` 중앙 함수로 Stop hook과 save_context.py 모두에서 보호한다.
- **근거**: 단일 기준(크기만)은 false positive/negative가 높다. 크기 OR 구조적 마커의 다중 신호가 더 정확하다.
- **대안**: 항상 덮어쓰기 → 기각 (데이터 유실), 크기만 비교 → 기각 (small-but-rich 케이스 미처리)
- **관련 커밋**: `f76a1fd` feat: P1 할루시네이션 봉쇄 + E5 Guard 중앙화

### ADR-017: Error Taxonomy 12패턴 + Error→Resolution 매칭

- **날짜**: 2026-02-19
- **상태**: Accepted
- **맥락**: Knowledge Archive에 에러 패턴을 기록할 때, "unknown" 분류가 대다수를 차지하여 cross-session 에러 분석이 불가능했다.
- **결정**: 12개 regex 패턴(file_not_found, permission, syntax, timeout, dependency, edit_mismatch, type_error, value_error, connection, memory, git_error, command_not_found)으로 에러를 분류한다. False positive 방지를 위해 negative lookahead, 한정어 매칭을 적용한다. 에러 발생 후 5 entries 이내의 성공적 도구 호출을 file-aware로 탐지하여 resolution을 기록한다.
- **근거**: 구조화된 에러 분류가 있어야 "이 에러를 과거에 어떻게 해결했는가"를 프로그래밍적으로 탐색할 수 있다. Resolution 매칭은 에러-해결 쌍을 자동으로 연결한다.
- **대안**: 에러 텍스트 그대로 기록 → 기각 (검색 불가, 패턴 분석 불가)
- **관련 커밋**: `ce0c393` fix: 2차 감사 22개 이슈 구현, `eed44e7` fix: 3차 성찰 5건 수정

### ADR-018: context_guard.py 통합 디스패처

- **날짜**: 2026-02-17
- **상태**: Accepted
- **맥락**: Global Hook(~/.claude/settings.json)에서 4개 이벤트(Stop, PostToolUse, PreCompact, SessionStart)를 각각 별도 스크립트로 연결하면 설정이 복잡하고, 공통 로직(경로 해석, 에러 핸들링)이 중복된다.
- **결정**: `context_guard.py`를 단일 진입점으로 사용하고, `--mode` 인자로 라우팅한다. Setup Hook만 프로젝트 설정에서 직접 실행한다 (세션 시작 전 인프라 검증이라 디스패처와 독립).
- **근거**: 단일 진입점은 유지보수가 쉽고, 공통 로직(경로, 에러)을 한 곳에서 관리할 수 있다.
- **대안**: 각 이벤트별 독립 스크립트 → 기각 (설정 복잡도 증가, 공통 로직 중복)
- **관련 커밋**: `0f38784` feat: Fix broken hooks + optimize context memory for quality

---

## 4. Automation Modes (자동화 모드)

### ADR-019: Autopilot Mode — Human Checkpoint 자동 승인

- **날짜**: 2026-02-17
- **상태**: Accepted
- **맥락**: 워크플로우 실행 시 `(human)` 단계마다 사용자가 직접 승인해야 하면, 장시간 워크플로우에서 사용자가 자리를 비울 수 없다.
- **결정**: `autopilot.enabled: true`로 SOT에 설정하면, `(human)` 단계와 `AskUserQuestion`을 품질 극대화 기본값으로 자동 승인한다. 단, Hook exit code 2는 변경 없이 차단한다 (결정론적 검증은 자동 대행 대상이 아님).
- **근거**: 사람의 판단만 AI가 대행하고, 코드의 결정론적 검증은 그대로 유지한다. 모든 자동 승인은 Decision Log에 기록하여 투명성을 보장한다.
- **대안**:
  - 완전 자동 (Hook 차단도 무시) → 기각 (품질 게이트 무력화)
  - 시간 기반 자동 승인 (N분 대기 후) → 기각 (인위적 대기, 비생산적)
- **관련 커밋**: `b0ae5ac` feat: Autopilot Mode runtime enforcement

### ADR-020: Autopilot 런타임 강화 — 하이브리드 Hook + 프롬프트

- **날짜**: 2026-02-17
- **상태**: Accepted
- **맥락**: Autopilot의 설계 의도(완전 실행, 축약 금지, Decision Log 기록)가 프롬프트만으로는 세션 경계에서 유실될 수 있다.
- **결정**: 하이브리드 강화 시스템을 구축한다:
  - **Hook (결정론적)**: SessionStart가 규칙 주입, 스냅샷이 IMMORTAL로 상태 보존, Stop이 Decision Log 누락 감지
  - **프롬프트 (행동 유도)**: Execution Checklist로 각 단계의 필수 행동 명시
- **근거**: Hook은 AI의 해석에 의존하지 않고 결정론적으로 동작한다. 프롬프트는 AI의 행동을 유도하지만 보장하지 못한다. 두 계층의 결합이 가장 강력하다.
- **대안**: 프롬프트만으로 → 기각 (세션 경계에서 유실), Hook만으로 → 기각 (세밀한 행동 유도 불가)
- **관련 커밋**: `b0ae5ac` feat: Autopilot Mode runtime enforcement

### ADR-021: Agent Team (Swarm) 패턴 — 2계층 SOT 프로토콜

- **날짜**: 2026-02-18
- **상태**: Accepted
- **맥락**: 병렬 에이전트가 동시에 작업할 때, SOT에 대한 동시 쓰기를 방지하면서도 팀원 간 산출물 참조가 가능해야 했다.
- **결정**: Team Lead만 SOT 쓰기 권한을 갖고, Teammate는 산출물 파일 생성만 한다. 품질 향상이 입증되는 경우에만 팀원 간 산출물 직접 참조를 허용한다 (교차 검증, 피드백 루프).
- **근거**: 절대 기준 2(SOT)와 절대 기준 1(품질)의 균형점. SOT 단일 쓰기는 유지하되, 품질을 위한 팀원 간 직접 참조는 예외로 허용한다.
- **대안**: 모든 팀원이 SOT 쓰기 → 기각 (절대 기준 2 위반), 팀원 간 완전 격리 → 기각 (교차 검증 불가)
- **관련 커밋**: `42ee4b1` feat: Agent Team(Swarm) 패턴 통합

### ADR-022: Verification Protocol — Anti-Skip Guard + Verification Gate + pACS

- **날짜**: 2026-02-19
- **상태**: Accepted
- **맥락**: Autopilot에서 산출물 없이 다음 단계로 넘어가거나, 형식적으로만 완료 표시하는 문제를 방지해야 했다.
- **결정**: 4계층 품질 보장 아키텍처를 도입한다:
  - **L0 Anti-Skip Guard** (결정론적): 산출물 파일 존재 + 최소 크기(100 bytes)
  - **L1 Verification Gate** (의미론적): 산출물이 Verification 기준을 100% 달성했는지 자기 검증
  - **L1.5 pACS Self-Rating** (신뢰도): Pre-mortem Protocol → F/C/L 3차원 채점 → RED(< 50) 시 재작업
  - **L2 Calibration** (선택적): 별도 verifier 에이전트가 pACS 교차 검증
- **근거**: 물리적 검증(파일 존재)과 의미론적 검증(내용 완전성)과 신뢰도 검증(약점 인식)은 서로 다른 차원이다. 각 계층이 독립적으로 다른 종류의 실패를 잡는다.
- **대안**: Anti-Skip Guard만 → 기각 (빈 파일도 통과 가능), Verification Gate만 → 기각 (AI의 자기 검증은 과대평가 경향)
- **관련 커밋**: `f592483` feat: Verification Protocol 추가

### ADR-023: ULW (Ultrawork) Mode — SOT 없이 동작하는 범용 모드

- **날짜**: 2026-02-20
- **상태**: Accepted
- **맥락**: Autopilot은 워크플로우 전용(SOT 기반)이지만, 워크플로우가 아닌 일반 작업(리팩토링, 문서 업데이트 등)에서도 "멈추지 않고 끝까지 완료하는" 모드가 필요했다.
- **결정**: `ulw`를 프롬프트에 포함하면 활성화되는 ULW 모드를 만든다. SOT 없이 5개 실행 규칙(Sisyphus, Auto Task Tracking, Error Recovery, No Partial Completion, Progress Reporting)으로 동작한다. 새 세션에서는 암묵적으로 해제된다 (명시적 해제 불필요).
- **근거**: Autopilot은 SOT 의존적이라 일반 작업에 부적합하다. ULW는 TaskCreate/TaskList 기반으로 경량화하여, 워크플로우 인프라 없이도 완료 보장을 제공한다.
- **대안**: Autopilot 확장 → 기각 (SOT 강제 요구는 일반 작업에 과도), 모드 없음 → 기각 (AI가 중간에 멈추는 문제 미해결)
- **관련 커밋**: `c7324f1` feat: ULW (Ultrawork) Mode 구현

---

## 5. Quality & Safety (품질 및 안전)

### ADR-024: P1 할루시네이션 봉쇄 — 4개 메커니즘

- **날짜**: 2026-02-20
- **상태**: Accepted
- **맥락**: Hook 시스템에서 반복적으로 100% 정확해야 하는 작업(스키마 검증, SOT 쓰기 방지 등)이 있는데, AI의 확률적 판단에 의존하면 hallucination 위험이 있다.
- **결정**: 4개 결정론적 메커니즘을 Python 코드로 구현한다:
  1. **KI 스키마 검증**: `_validate_session_facts()` — 10개 필수 키 보장
  2. **부분 실패 격리**: archive 실패가 index 갱신을 차단하지 않음
  3. **SOT 쓰기 패턴 검증**: AST 기반으로 Hook 스크립트의 SOT 쓰기 시도 탐지
  4. **SOT 스키마 검증**: `validate_sot_schema()` — 6항목 구조 무결성
- **근거**: "반복적으로 100% 정확해야 하는 작업"은 AI가 아닌 코드가 수행해야 한다 (P1 원칙의 극단적 적용). 코드는 hallucinate하지 않는다.
- **대안**: AI에게 스키마 검증 요청 → 기각 (확률적, 누락 가능성), 검증 없이 운영 → 기각 (silent corruption 위험)
- **관련 커밋**: `f76a1fd` feat: P1 할루시네이션 봉쇄 + E5 Guard 중앙화

### ADR-025: Atomic Write 패턴 — Crash-safe 파일 쓰기

- **날짜**: 2026-02-18
- **상태**: Accepted
- **맥락**: Hook 스크립트가 스냅샷, 아카이브, 로그를 쓰는 도중 프로세스가 크래시하면, 부분 쓰기로 파일이 손상될 수 있다.
- **결정**: 모든 파일 쓰기에 atomic write 패턴(temp file → `os.rename`)을 적용한다. `fcntl.flock`으로 동시 접근을 보호하고, `os.fsync()`로 내구성을 보장한다.
- **근거**: `os.rename`은 POSIX에서 atomic이므로, 중간 상태가 노출되지 않는다. 프로세스 크래시 시에도 이전 상태가 온전히 유지된다.
- **대안**: 직접 쓰기 → 기각 (크래시 시 부분 쓰기), 데이터베이스 트랜잭션 → 기각 (오버엔지니어링)
- **관련 커밋**: `2c91985` feat: Context Preservation 품질 강화

### ADR-026: 결정 품질 태그 정렬 — IMMORTAL 슬롯 최적화

- **날짜**: 2026-02-19
- **상태**: Accepted
- **맥락**: 스냅샷의 "주요 설계 결정" 섹션(15개 슬롯)에서 일상적 의도 선언("하겠습니다" 패턴)이 실제 설계 결정을 밀어내는 문제가 있었다.
- **결정**: 4단계 품질 태그 기반 정렬을 도입한다: `[explicit]` > `[decision]` > `[rationale]` > `[intent]`. 비교·트레이드오프·선택 패턴도 추출하여, 고신호 결정이 15개 슬롯을 우선 차지한다.
- **근거**: 한정된 슬롯에서 "하겠습니다"보다 "A 대신 B를 선택했다, 이유는..."이 복원 시 훨씬 더 가치 있다.
- **대안**: 시간순 → 기각 (최근 intent가 오래된 decision을 밀어냄), 필터링 없음 → 기각 (노이즈가 신호를 압도)
- **관련 커밋**: `2c91985` feat: Context Preservation 품질 강화

---

## 6. Language & Translation (언어 및 번역)

### ADR-027: English-First 실행 원칙

- **날짜**: 2026-02-17
- **상태**: Accepted
- **맥락**: 사용자와의 대화는 한국어지만, AI 에이전트의 작업 품질은 영어에서 가장 높다. 한국어로 직접 산출물을 생성하면 품질이 떨어진다.
- **결정**: 워크플로우 실행 시 모든 에이전트는 영어로 작업하고 영어로 산출물을 생성한다. 한국어는 별도 번역 프로토콜로 제공한다.
- **근거**: 절대 기준 1(품질)의 직접적 구현. AI는 영어에서 가장 높은 성능을 발휘하므로, 영어 우선 실행이 최고 품질을 보장한다.
- **대안**: 한국어로 직접 생성 → 기각 (품질 저하), 언어 선택을 사용자에게 위임 → 기각 (일관성 없음)
- **관련 커밋**: `5b649cb` feat: Hub-and-Spoke universal system prompt

### ADR-028: @translator 서브에이전트 + glossary 영속 상태

- **날짜**: 2026-02-17
- **상태**: Accepted
- **맥락**: 영어 산출물을 한국어로 번역할 때, 단순 번역 도구로는 도메인 용어의 일관성을 보장할 수 없다.
- **결정**: `@translator` 서브에이전트를 정의하고, `translations/glossary.yaml`을 RLM 외부 영속 상태로 유지한다. 번역 시 glossary를 참조하여 용어 일관성을 보장하고, 새 용어는 glossary에 추가한다.
- **근거**: RLM의 Variable Persistence 패턴 적용. glossary가 서브에이전트 호출 간 상태를 유지하여, 번역 품질이 세션을 거듭할수록 향상된다.
- **대안**: 매번 번역 규칙 재지정 → 기각 (용어 불일치), 외부 번역 API → 기각 (도메인 특화 용어 미지원)
- **관련 커밋**: `5b649cb` feat: Hub-and-Spoke universal system prompt

---

## 7. Infrastructure (인프라)

### ADR-029: Setup Hook — 세션 시작 전 인프라 건강 검증

- **날짜**: 2026-02-19
- **상태**: Accepted
- **맥락**: Hook 스크립트가 Python 환경, PyYAML, 디렉터리 구조 등에 의존하는데, 이것들이 깨져 있으면 모든 Hook이 silent failure한다.
- **결정**: `setup_init.py`를 Setup Hook(`claude --init`)으로 등록하여, 세션 시작 전 7개 항목(Python 버전, PyYAML, 스크립트 구문 ×6, 디렉터리 ×2, .gitignore, SOT 쓰기 패턴)을 자동 검증한다.
- **근거**: "작동한다고 가정하지 말고, 매번 검증하라." Hook이 silent failure하면 컨텍스트 보존이 완전히 무력화되므로, 사전 검증이 필수적이다.
- **대안**: 수동 점검 → 기각 (까먹기 쉬움), 첫 실행 시 자동 설치 → 기각 (사용자 환경에 무단 설치)
- **관련 커밋**: `2c91985` feat: Context Preservation 품질 강화

### ADR-030: 절삭 상수 중앙화 — 10개 상수

- **날짜**: 2026-02-19
- **상태**: Accepted
- **맥락**: 스냅샷 생성 시 Edit preview, Error message 등의 길이를 절삭하는 상수가 여러 함수에 하드코딩되어 있어, 일관성 없는 절삭이 발생했다.
- **결정**: `_context_lib.py`에 10개 절삭 상수(`EDIT_PREVIEW_CHARS=1000`, `ERROR_RESULT_CHARS=3000`, `MIN_OUTPUT_SIZE=100` 등)를 중앙 정의한다.
- **근거**: 중앙 정의된 상수는 한 곳만 수정하면 전체에 반영된다. Edit preview는 5줄 × 1000자로 편집 의도·맥락을 보존하고, 에러 메시지는 3000자로 stack trace 전체를 보존한다.
- **대안**: 각 함수에 인라인 → 기각 (값 불일치 위험, 튜닝 시 누락)
- **관련 커밋**: `2c91985` feat: Context Preservation 품질 강화

### ADR-031: PreToolUse Safety Hook — 위험 명령 차단

- **날짜**: 2026-02-20
- **상태**: Accepted
- **맥락**: Claude Code의 6개 차단 가능 Hook 이벤트 중 PreToolUse만 미구현. 위험한 Git/파일 명령(git push --force, git reset --hard, rm -rf / 등)이 AI 판단에만 의존하여 실행될 수 있었다.
- **결정**: `block_destructive_commands.py`를 PreToolUse Hook(matcher: Bash)으로 등록. 10개 패턴(9개 정규식 + 1개 절차적 rm 검사)으로 위험 명령을 결정론적으로 탐지하고, exit code 2로 차단 + stderr 피드백으로 Claude 자기 수정을 유도한다.
- **근거**: P1 할루시네이션 봉쇄 — 위험 명령 탐지는 정규식으로 100% 결정론적. AI 판단 개입 없음. `context_guard.py`를 거치지 않는 독립 실행 — `|| true` 패턴이 exit code 2를 삼키는 문제 회피를 위해 `if test -f; then; fi` 패턴 사용.
- **대안**: (1) SOT 쓰기 보호 → 보류 (Hook API가 에이전트 역할을 구분하지 못함), (2) Anti-Skip Guard 강화 → 보류 (Stop 타이밍이 사후적이어서 예방 불가)
- **차단 패턴**: git push --force(NOT --force-with-lease), git push -f, git reset --hard, git checkout ., git restore ., git clean -f, git branch -D, git branch --delete --force(양방향 순서), rm -rf / 또는 ~

### ADR-032: PreToolUse TDD Guard — 테스트 파일 수정 차단

- **날짜**: 2026-02-20
- **상태**: Accepted
- **맥락**: Claude는 TDD 시 테스트가 실패하면 구현 코드 대신 테스트 코드를 수정하려는 경향이 있다. 이는 TDD의 핵심 원칙("테스트는 불변, 구현만 수정")을 위반한다.
- **결정**: `block_test_file_edit.py`를 PreToolUse Hook(matcher: `Edit|Write`)으로 등록한다. `.tdd-guard` 파일이 프로젝트 루트에 존재할 때만 활성화된다. 2계층 탐지(Tier 1: 디렉터리명 — test/tests/__tests__/spec/specs, Tier 2: 파일명 패턴 — test_*/\*_test.\*/\*.test.\*/\*.spec.\*/\*Test.\*/conftest.py)로 테스트 파일을 결정론적으로 식별하고, exit code 2 + stderr 피드백으로 Claude가 구현 코드를 수정하도록 유도한다.
- **근거**:
  - P1 할루시네이션 봉쇄 패턴 재사용 — 테스트 파일 탐지는 regex/string matching으로 100% 결정론적
  - ADR-031(`block_destructive_commands.py`)과 동일한 아키텍처 — 독립 실행, `if test -f; then; fi` 패턴, Safety-first exit(0)
  - `.tdd-guard` 토글은 SOT(`state.yaml`)와 독립 — TDD는 워크플로우 밖에서도 사용되므로 SOT 의존 부적합
  - `REQUIRED_SCRIPTS`(D-7) 양쪽 동기화로 `setup_init.py`/`setup_maintenance.py` 인프라 검증 대상에 포함
- **대안**:
  - 항상 차단 (토글 없음) → 기각 (테스트 작성 시에도 차단되어 비실용적)
  - SOT `tdd_mode: true`로 제어 → 기각 (SOT는 워크플로우 전용, TDD는 범용)
  - PostToolUse에서 사후 경고 → 기각 (이미 파일이 수정된 후라 예방 불가)
- **관련 커밋**: (pending)

### ADR-033: Context Memory 최적화 — success_patterns + Next Step IMMORTAL + 모듈 레벨 regex

- **날짜**: 2026-02-20
- **상태**: Accepted
- **맥락**: 전체 감사 결과 3가지 Context Memory 최적화 기회가 확인되었다. (1) Knowledge Archive가 error_patterns만 기록하고 성공 패턴은 누락, (2) "다음 단계" 섹션이 독립 IMMORTAL 마커 없이 부모 섹션에 암묵적 포함, (3) `_extract_decisions()`의 8개 regex + `_extract_next_step()`의 1개 regex + `_SYSTEM_CMD`가 매 호출마다 컴파일.
- **결정**:
  1. `_extract_success_patterns()` 함수 추가 — Edit/Write→성공적 Bash 시퀀스를 결정론적으로 추출하여 `success_patterns` 필드로 Knowledge Archive에 기록
  2. "다음 단계 (Next Step)" 섹션을 독립 `## ` 헤더 + `<!-- IMMORTAL: -->` 마커로 승격 — Phase 7 hard truncate에서 명시적 보존 대상
  3. 10개 regex 패턴을 모듈 레벨 상수로 이동 — 프로세스당 1회 컴파일
- **근거**:
  - success_patterns: `Grep "success_patterns" knowledge-index.jsonl`로 RLM cross-session 성공 패턴 탐색 가능. error_patterns의 대칭 — 실패에서 배우듯 성공에서도 배운다.
  - Next Step IMMORTAL: 세션 복원 시 "다음에 무엇을 해야 하는지"는 "현재 무엇을 하고 있는지" 못지않게 중요한 인지적 연속성 앵커.
  - 모듈 레벨 regex: Stop hook 30초 간격 실행에서 매번 10개 패턴을 재컴파일하는 것은 불필요한 오버헤드.
- **대안**:
  - success_patterns에 Read도 포함 → 기각 (Read는 검증 아닌 탐색이므로 "성공 패턴"으로서 신호 약함)
  - Next Step을 별도 파일로 분리 → 기각 (over-engineering, 스냅샷 내 IMMORTAL 마커로 충분)
- **관련 커밋**: (pending)

### ADR-034: Adversarial Review — Enhanced L2 품질 계층 + P1 할루시네이션 봉쇄

- **날짜**: 2026-02-20
- **상태**: Accepted
- **맥락**: Generator-Critic 패턴(적대적 에이전트)을 도입하여 환각을 줄이고 산출물 품질을 높이고자 했다. 기존 L2 Calibration은 "선택적 교차 검증"으로서 구체적 구현이 없었다. 연구·개발 작업 모두에서 독립적 비판적 검토가 필요했다. 3차례의 심층 성찰(Critical Reflection)을 거쳐 설계를 확정했다.
- **결정**:
  1. 기존 L2 Calibration을 **Adversarial Review (Enhanced L2)**로 대체 — `@reviewer`(코드/산출물 분석, 읽기 전용)와 `@fact-checker`(사실 검증, 웹 접근) 두 전문 에이전트 신설
  2. `Review:` 필드를 워크플로우 단계 속성으로 추가 (기존 `Translation:` 패턴과 동일)
  3. P1 결정론적 검증 4개 함수를 `_context_lib.py`에 추가: `validate_review_output()` (R1-R5 5개 체크), `parse_review_verdict()` (regex 기반 이슈 추출), `calculate_pacs_delta()` (Generator-Reviewer 점수 산술 비교), `validate_review_sequence()` (Review→Translation 순서 타임스탬프 검증)
  4. Rubber-stamp 방지 4계층: 적대적 페르소나 + Pre-mortem 필수 + 최소 1개 이슈 (P1 R5) + 독립 pACS 채점
  5. 실행 순서: L0 → L1 → L1.5 → Review(L2) → PASS → Translation
  6. Stop hook에 Review 누락 감지 안전망 추가 (`_check_missing_reviews()`)
- **근거**:
  - **Enhanced L2 위치**: 기존 L2가 이미 "교차 검증"이므로 적대적 검토는 이를 엄격하게 구현한 것. 새 L3를 만드는 것보다 기존 계층을 강화하는 것이 아키텍처 복잡도를 낮춘다.
  - **2개 에이전트 분리 (P2)**: 코드 논리 분석(Read-only)과 사실 검증(WebSearch)은 필요 도구가 완전히 다르다. 최소 권한 원칙에 의해 분리.
  - **Sub-agent 선택**: 리뷰 결과를 즉시 반영하는 동기적 피드백 루프가 필요하므로 Agent Team 비동기 패턴보다 Sub-agent가 품질 극대화에 유리.
  - **P1 필요성**: 리뷰 보고서 존재/구조/verdict/이슈 수/pACS delta 검증은 100% 정확해야 하는 반복 작업으로, LLM에 맡기면 hallucination 위험. Python regex/filesystem/arithmetic으로 강제.
- **대안**:
  - 단일 `@critic` 에이전트 → 기각 (코드 분석과 사실 검증의 도구 프로파일이 다름)
  - 새 `(adversarial)` 단계 유형 → 기각 (`Review:` 속성이 기존 `Translation:` 패턴과 일관적이며 하위 호환)
  - L3 신설 → 기각 (기존 L2를 강화하는 것이 더 간결)
  - Reviewer가 직접 파일을 수정 → 기각 (읽기 전용이어야 Generator와의 역할 분리 유지)
- **관련 커밋**: (pending)

### ADR-035: 종합 감사 — SOT 스키마 확장 + Quality Gate IMMORTAL + Error→Resolution 표면화

- **날짜**: 2026-02-20
- **상태**: Accepted
- **맥락**: 코드베이스 전체에 대한 종합 감사에서 6가지 미구현·미최적화 영역이 발견되었다. (1) pacs/active_team SOT 스키마 미검증, (2) Quality Gate 상태의 세션 경계 유실, (3) 이전 세션 에러 해결 경험의 수동 Grep 의존, (4) 런타임 디렉터리 부재 시 silent failure, (5) 다단계 전환 정보의 스냅샷 헤더 미반영, (6) CLAUDE.md 문서와 구현의 불일치. 이 중 (2)와 (3)은 Context Memory 품질 최적화 관점에서 특히 중요했다.
- **결정**:
  1. `validate_sot_schema()` 확장: S7(pacs 구조 — dimensions F/C/L 0-100, current_step_score, weak_dimension) + S8(active_team — name, status 유효값) 검증 추가 → 6항목 → 8항목
  2. `_extract_quality_gate_state()` 신설: pacs-logs/, review-logs/, verification-logs/에서 최신 단계의 품질 게이트 결과를 추출하여 IMMORTAL 스냅샷 섹션으로 보존
  3. `_extract_recent_error_resolutions()` 신설(restore_context.py): Knowledge Archive에서 최근 에러→해결 패턴을 읽어 SessionStart 출력에 최대 3개 자동 표시
  4. `_check_runtime_dirs()` 신설(setup_init.py): SOT 존재 시 verification-logs/, pacs-logs/, review-logs/, autopilot-logs/ 자동 생성
  5. 스냅샷 헤더에 Phase Transition 흐름 표시: 다단계 세션에서 `Phase flow: research(12) → implementation(25)` 형식
  6. CLAUDE.md 전체 동기화: 프로젝트 트리, 동작 원리 테이블, Claude 활용 방법 3개 레벨 일관성 확보
- **근거**:
  - **Quality Gate IMMORTAL**: compact/clear 후 Verification Gate/pACS/Review 진행 상태가 유실되면 다음 단계 진입 시 잘못된 판단 위험 → IMMORTAL로 보존하여 세션 경계에서의 품질 게이트 연속성 보장 (절대 기준 1)
  - **Error→Resolution 표면화**: 수동 Grep 의존 시 이전 세션의 해결 경험이 활용되지 않음 → SessionStart에서 자동 표시하여 동일 에러 재발 시 즉시 해결 가능 (RLM 패턴의 프로액티브 활용)
  - **SOT 스키마 확장**: pacs와 active_team은 Autopilot 실행의 핵심 상태이나 스키마 검증이 없어 hallucination에 취약 → P1 결정론적 검증으로 봉쇄
  - **런타임 디렉터리**: 디렉터리 부재 시 파일 쓰기가 조용히 실패하여 Verification/pACS/Review 로그가 유실됨 → Setup 시 사전 생성
- **대안**:
  - Quality Gate 상태를 SOT에 저장 → 기각 (Hook은 SOT 쓰기 금지 — 절대 기준 2)
  - Error→Resolution을 스냅샷 본문에 포함 → 기각 (스냅샷 크기 증가, SessionStart 출력이 더 즉각적)
  - 런타임 디렉터리를 각 Hook에서 개별 생성 → 기각 (Setup에서 한 번 검증이 더 효율적이고 결정론적)
- **관련 커밋**: (pending)

---

## 부록: 커밋 히스토리 기반 타임라인

| 날짜 | 커밋 | 결정 |
|------|------|------|
| 2026-02-16 | `348601e` | ADR-001~007: 프로젝트 기반 (목표, 절대 기준, 3단계 구조, SOT, CCP) |
| 2026-02-16 | `e051837` | ADR-009: RLM 이론적 기반 채택 |
| 2026-02-16 | `feba502` | ADR-010: 독립 아키텍처 문서 분리 |
| 2026-02-16 | `bb7b9a1` | ADR-012: Hook 기반 컨텍스트 보존 시스템 |
| 2026-02-17 | `d1acb9f` | ADR-013: Knowledge Archive |
| 2026-02-17 | `7363cc4` | ADR-014: Smart Throttling |
| 2026-02-17 | `5b649cb` | ADR-008, 027, 028: Hub-and-Spoke, English-First, @translator |
| 2026-02-17 | `b0ae5ac` | ADR-019, 020: Autopilot Mode + 런타임 강화 |
| 2026-02-18 | `42ee4b1` | ADR-021: Agent Team (Swarm) 패턴 |
| 2026-02-18~19 | `2c91985` | ADR-015, 025, 026, 029, 030: 18항목 감사·성찰 |
| 2026-02-19 | `f592483` | ADR-022: Verification Protocol |
| 2026-02-19 | `ce0c393`, `eed44e7` | ADR-017: Error Taxonomy |
| 2026-02-20 | `c7324f1` | ADR-023: ULW Mode |
| 2026-02-20 | `162a322`~`5634b0e` | ADR-011: Spoke 파일 정리 |
| 2026-02-20 | `f76a1fd` | ADR-016, 024: E5 Guard, P1 할루시네이션 봉쇄 |
| 2026-02-20 | (pending) | ADR-031: PreToolUse Safety Hook |
| 2026-02-20 | (pending) | ADR-032: PreToolUse TDD Guard |
| 2026-02-20 | (pending) | ADR-033: Context Memory 최적화 (success_patterns, Next Step IMMORTAL, regex) |
| 2026-02-20 | (pending) | ADR-034: Adversarial Review — Enhanced L2 + P1 할루시네이션 봉쇄 |
| 2026-02-20 | (pending) | ADR-035: 종합 감사 — SOT 스키마 확장 + Quality Gate IMMORTAL + Error→Resolution 표면화 |

---

## 문서 관리

- **갱신 규칙**: 새로운 `feat:` 커밋이 설계 결정을 포함하면, 해당 ADR을 이 문서에 추가한다.
- **번호 규칙**: `ADR-NNN` 형식으로 순차 부여. 삭제된 번호는 재사용하지 않는다.
- **상태 전이**: `Accepted` → `Superseded by ADR-NNN` → `Deprecated` (사유 명시)
- **위치**: 프로젝트 루트 (`DECISION-LOG.md`). 프로젝트 구조 트리에 포함.
