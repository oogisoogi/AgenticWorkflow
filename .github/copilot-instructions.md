# AgenticWorkflow — GitHub Copilot 지시서

> 이 프로젝트에서 작업하는 모든 AI는 AgenticWorkflow 방법론을 따라야 한다.

## 필수 참조

이 프로젝트의 모든 절대 기준, 설계 원칙, 워크플로우 구조는 `AGENTS.md`에 정의되어 있다.
Copilot CLI는 `AGENTS.md`를 자동으로 인식하므로, 해당 파일의 모든 규칙이 자동 적용된다.
상세 아키텍처는 `AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md`를 참조한다.

## 절대 기준 (핵심 요약)

1. **품질 최우선** — 속도, 비용, 작업량보다 최종 결과물의 품질이 유일한 기준
2. **단일 파일 SOT** — 모든 공유 상태는 단일 파일에 집중. 쓰기 권한은 Orchestrator만
3. **코드 변경 프로토콜** — 의도 파악 → 영향 범위 분석 → 변경 설계 3단계 수행. 분석 깊이는 변경 규모에 비례

> **상세 내용**: AGENTS.md §2 참조.

## 워크플로우 구조

모든 워크플로우는 3단계: **Research** → **Planning** → **Implementation**.

## Copilot 구현 매핑

| AgenticWorkflow 개념 | Copilot 대응 |
|---------------------|-------------|
| 전문 에이전트 | Copilot의 단일 세션 내 역할 지정 |
| 자동 검증 | GitHub Actions 또는 외부 스크립트로 구현 |
| SOT 상태관리 | `state.yaml` 파일 — 단일 쓰기 지점 원칙 동일 적용. SOT 파일 형식: `state.yaml`, `state.yml`, `state.json` |
| Autopilot Mode | SOT의 `autopilot.enabled` 필드로 제어. `(human)` 단계 자동 승인. Anti-Skip Guard: 산출물 파일 존재 + 최소 100 bytes 검증. `AGENTS.md §5.1` 참조 |

## 컨텍스트 보존

Copilot CLI에는 자동 Hook 기반 컨텍스트 보존이 없다. 대안:

- **수동 저장**: 작업 진행 시 `state.yaml`에 현재 상태 기록
- **세션 재개**: `/resume SESSION-ID`로 이전 세션 이어가기
- **스냅샷**: 중요 시점에 작업 내역을 MD 파일로 수동 저장

> Claude Code의 Context Preservation System은 5개 Hook으로 자동 저장·복원하며, Knowledge Archive에 세션별 phase(단계), phase_flow(전환 흐름), primary_language(주요 언어) 메타데이터를 자동 기록한다. Copilot에서는 이 정보를 `state.yaml`에 수동 기록하거나, 스냅샷 MD 파일에 세션 메타데이터를 포함하는 방식으로 대응한다.

## 설계 원칙

- **P1**: AI에게 전달하기 전 Python 등으로 노이즈 제거 (전처리/후처리 명시)
- **P2**: 전문 에이전트에게 위임하여 품질 극대화
- **P3**: 리소스의 정확한 경로 명시. placeholder 누락 불가
- **P4**: 사용자 질문은 최대 4개, 각 3개 선택지

## 언어 및 스타일

- **콘텐츠**: 한국어 / **기술 용어**: 영어 유지 / **시각화**: Mermaid 선호
