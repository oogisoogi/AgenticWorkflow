# AgenticWorkflow — Gemini CLI 지시서

> 이 프로젝트에서 작업하는 모든 AI는 AgenticWorkflow 방법론을 따라야 한다.

## 필수 참조

@AGENTS.md

위 파일은 이 프로젝트의 모든 절대 기준, 설계 원칙, 워크플로우 구조를 정의한다.
상세 아키텍처는 `AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md`를 참조한다.

## 절대 기준 (핵심 요약)

### 절대 기준 1: 최종 결과물의 품질

> 속도, 토큰 비용, 작업량, 분량 제한은 완전히 무시한다.
> 모든 의사결정의 유일한 기준은 **최종 결과물의 품질**이다.

### 절대 기준 2: 단일 파일 SOT

> 모든 공유 상태는 단일 파일에 집중한다. 쓰기 권한은 Orchestrator만 보유한다.
> 병렬 에이전트가 동일 파일을 동시 수정하는 구조는 금지한다.

### 절대 기준 3: 코드 변경 프로토콜 (CCP)

> 코드를 작성·수정·추가·삭제하기 전에 반드시 3단계를 수행한다:
> Step 1 의도 파악 → Step 2 영향 범위 분석 → Step 3 변경 설계.
> 분석 깊이는 변경 규모에 비례한다 (경미: Step 1만, 표준: 전체, 대규모: 전체 + 사용자 승인).

> **상세 내용**: AGENTS.md §2 참조.

## 워크플로우 구조

모든 워크플로우는 3단계로 구성된다:

1. **Research** — 정보 수집 및 분석
2. **Planning** — 계획 수립, 구조화, 사람의 검토/승인
3. **Implementation** — 실제 실행 및 산출물 생성

## Gemini CLI 구현 매핑

| AgenticWorkflow 개념 | Gemini CLI 대응 |
|---------------------|----------------|
| 전문 에이전트 (Sub-agent) | Gemini CLI는 단일 세션 모델. 프롬프트 내에서 역할을 전환하여 전문성 시뮬레이션 |
| 에이전트 그룹 (Agent Team) | 별도 Gemini 세션을 병렬로 실행하여 구현 |
| 자동 검증 (Hooks) | 외부 셸 스크립트로 검증 파이프라인 구성 |
| 재사용 모듈 (Skills) | `@file.md` import로 도메인 지식 주입 |
| 외부 연동 (MCP) | Gemini extensions 또는 외부 API 스크립트 |
| SOT 상태관리 | `state.yaml` 파일 — 단일 쓰기 지점 원칙 동일 적용 |
| Autopilot Mode | SOT의 `autopilot.enabled` 필드로 제어. `(human)` 단계 자동 승인. Anti-Skip Guard(산출물 검증), Decision Log(`autopilot-logs/`) 포함. `AGENTS.md §5.1` 참조 |
| Verification Protocol | 각 단계 산출물의 기능적 목표 100% 달성 검증. Anti-Skip Guard(물리적) 위에 의미론적 Verification Gate 계층. 검증 기준은 Task 앞에 선언, 실패 시 최대 2회 재시도. `AGENTS.md §5.3` 참조 |
| pACS (자체 신뢰 평가) | Verification Gate 통과 후 에이전트가 F/C/L 3차원 자기 평가. Pre-mortem Protocol 필수. min-score 원칙. GREEN(≥70): 자동 진행, YELLOW(50-69): 플래그 후 진행, RED(<50): 재작업. `AGENTS.md §5.4` 참조 |

## 컨텍스트 보존

Gemini CLI에는 Claude Code의 자동 Hook 기반 컨텍스트 보존 시스템이 없다. 대안:

- **수동 저장**: 작업 중간에 `작업 내역을 context-snapshot.md로 저장해줘` 지시
- **세션 로그**: Gemini CLI의 `/memory` 기능으로 핵심 사항 기억
- **SOT 기반 복원**: `state.yaml`에 워크플로우 진행 상태를 기록하여 새 세션에서 복원

> Claude Code의 Context Preservation System은 Knowledge Archive에 세션별 phase(단계), phase_flow(전환 흐름), primary_language(주요 언어) 메타데이터를 자동 기록하고, 스냅샷의 설계 결정은 품질 태그 우선순위(`[explicit]` > `[decision]` > `[rationale]` > `[intent]`)로 정렬하여 노이즈를 제거한다. 모든 파일 쓰기에 atomic write(temp → rename) 패턴을 적용한다. Gemini에서는 이 정보를 수동으로 기록하거나, 세션 종료 시 상태를 `state.yaml`에 요약하는 방식으로 대응한다.

## 설계 원칙

- **P1**: AI에게 전달하기 전 Python 등으로 노이즈 제거 (전처리/후처리 명시)
- **P2**: 전문 에이전트에게 위임하여 품질 극대화
- **P3**: 이미지/리소스의 정확한 경로 명시. placeholder 누락 불가
- **P4**: 사용자 질문은 최대 4개, 각 3개 선택지. 모호함 없으면 질문 없이 진행

## 언어 및 스타일

- **프레임워크 문서·사용자 대화**: 한국어
- **워크플로우 실행**: 영어 (AI 성능 극대화 — 절대 기준 1 근거). 상세: AGENTS.md §5.2
- **최종 산출물**: 영어 원본 + 한국어 번역 쌍 (`@translator` 서브에이전트)
- **기술 용어**: 영어 유지 (SOT, Agent, Orchestrator, Hooks 등)
- **시각화**: Mermaid 다이어그램 선호
- **깊이**: 간략 요약보다 포괄적·데이터 기반 서술 선호
