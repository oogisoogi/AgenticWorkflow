# AgenticWorkflow

에이전트 기반 워크플로우 자동화 프로젝트.

복잡한 작업을 **워크플로우로 설계**하고, 그 워크플로우를 **실제로 구현**하여 동작시키는 것이 목표입니다.

## 프로젝트 목표

```
Phase 1: 워크플로우 설계  →  workflow.md (설계도)
Phase 2: 워크플로우 구현  →  실제 동작하는 시스템 (최종 산출물)
```

워크플로우를 만드는 것은 중간 산출물입니다. **워크플로우에 기술된 내용이 실제로 동작하는 것**이 최종 목표입니다.

## 워크플로우 구조

모든 워크플로우는 3단계로 구성됩니다:

1. **Research** — 정보 수집 및 분석
2. **Planning** — 계획 수립, 구조화, 사람의 검토/승인
3. **Implementation** — 실제 실행 및 산출물 생성

## 프로젝트 구조

```
AgenticWorkflow/
├── CLAUDE.md              # Claude Code 전용 지시서
├── AGENTS.md              # 모든 AI 에이전트 공통 지시서
├── AGENTICWORKFLOW-USER-MANUAL.md              # 사용자 매뉴얼
├── AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md  # 설계 철학 및 아키텍처 전체 조감도
├── .claude/skills/
│   ├── workflow-generator/ # 워크플로우 설계·생성 스킬
│   └── doctoral-writing/   # 박사급 학술 글쓰기 스킬
├── prompt/                 # 프롬프트 자료
└── coding-resource/        # 이론적 기반 자료
    └── recursive language models.pdf
```

## 스킬

| 스킬 | 설명 |
|------|------|
| **workflow-generator** | Research → Planning → Implementation 3단계 구조의 `workflow.md`를 설계·생성. Sub-agents, Agent Teams, Hooks, Skills를 조합한 구현 설계 포함. |
| **doctoral-writing** | 박사급 학위 논문의 학문적 엄밀성과 명료성을 갖춘 글쓰기 지원. 한국어·영어 모두 지원. |

## 절대 기준

이 프로젝트의 모든 설계·구현 의사결정에 적용되는 최상위 규칙:

1. **품질 최우선** — 속도, 비용, 작업량보다 최종 결과물의 품질이 유일한 기준
2. **단일 파일 SOT** — Single Source of Truth + 계층적 메모리 구조로 데이터 일관성 보장
3. **품질 > SOT** — 두 기준이 충돌하면 품질이 우선. SOT는 수단이지 목적이 아님

## 이론적 기반

`coding-resource/recursive language models.pdf` — 장기기억(long-term memory) 구현에 필수적인 이론을 담은 논문입니다. 에이전트가 세션을 넘어 지식을 축적하고 활용하는 메커니즘의 이론적 토대입니다.

## AI 도구 호환성

| 파일 | 대상 |
|------|------|
| `CLAUDE.md` | Claude Code |
| `AGENTS.md` | Cursor, Copilot, Codex, Windsurf 등 모든 AI 코딩 도구 |

두 파일의 절대 기준과 설계 원칙은 동일합니다. 차이는 도구별 구현 매핑의 구체성뿐입니다.

## 매뉴얼

이 코드베이스 자체의 사용법은 [`AGENTICWORKFLOW-USER-MANUAL.md`](AGENTICWORKFLOW-USER-MANUAL.md)를 참조하세요.

> 이 코드베이스로 만든 개별 프로젝트의 사용법과 혼동하지 마세요.
> 개별 프로젝트의 매뉴얼은 해당 프로젝트 내에 별도로 존재합니다.
