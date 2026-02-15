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

### 절대 기준 간 우선순위

> **절대 기준 1(품질)과 절대 기준 2(SOT)가 충돌할 경우, 절대 기준 1이 우선한다.**
> SOT는 품질을 보장하기 위한 **수단**이지, 품질을 제약하는 **목적**이 아니다.

---

## 프로젝트 구조

```
AgenticWorkflow/
├── CLAUDE.md                              ← 이 파일 (Claude Code 전용 지시서)
├── AGENTS.md                              ← 모든 AI 에이전트 공통 지시서
├── README.md                              ← 프로젝트 소개
├── AGENTICWORKFLOW-USER-MANUAL.md         ← 이 코드베이스 자체의 사용자 매뉴얼
├── AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md  ← 설계 철학 및 아키텍처 전체 조감도
├── COPYRIGHT.md                           ← 저작권
├── .claude/
│   ├── settings.json                      ← Hook 설정 (SessionEnd)
│   ├── hooks/scripts/                     ← Context Preservation System
│   │   ├── _context_lib.py                (공유 라이브러리 — 파싱, 생성, SOT 캡처)
│   │   ├── save_context.py                (SessionEnd/PreCompact 저장 엔진)
│   │   ├── restore_context.py             (SessionStart 복원 — RLM 포인터)
│   │   ├── update_work_log.py             (PostToolUse 작업 로그 누적)
│   │   └── generate_context_summary.py    (Stop 증분 스냅샷)
│   ├── context-snapshots/                 ← 런타임 스냅샷 (gitignored)
│   └── skills/
│       ├── workflow-generator/            ← 워크플로우 설계·생성 스킬
│       │   ├── SKILL.md
│       │   └── references/                (claude-code-patterns, workflow-template, document-analysis-guide)
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
| **SessionEnd** (`/clear`) | `save_context.py` | 전체 대화·작업 내역을 MD 스냅샷으로 저장 |
| **PreCompact** | `save_context.py` | 컨텍스트 압축 전 스냅샷 저장 |
| **SessionStart** | `restore_context.py` | RLM 패턴: 포인터 + 요약을 stdout으로 출력 |
| **PostToolUse** | `update_work_log.py` | 작업 로그 누적. 토큰 75% 초과 시 proactive 저장 |
| **Stop** | `generate_context_summary.py` | 매 응답 후 증분 스냅샷 |

### Claude의 활용 방법

- 세션 시작 시 `[CONTEXT RECOVERY]` 메시지가 표시되면, 안내된 경로의 파일을 **반드시 Read tool로 읽어** 이전 맥락을 복원한다.
- 스냅샷은 `.claude/context-snapshots/latest.md`에 저장된다.
- Hook 스크립트는 SOT(`state.yaml`)를 **읽기 전용**으로만 접근한다 (절대 기준 2 준수).

### Hook 설정 위치

- **Global** (`~/.claude/settings.json`): PreCompact, SessionStart, PostToolUse, Stop
- **Project** (`.claude/settings.json`): SessionEnd

## 스킬 사용 판별

| 사용자 요청 패턴 | 스킬 | 진입점 |
|----------------|------|--------|
| "워크플로우 만들어줘", "자동화 파이프라인 설계", "작업 흐름 정의" | `workflow-generator` | SKILL.md → 케이스 판별 |
| "논문 스타일로 써줘", "학술적 글쓰기", "논문 문장 다듬기" | `doctoral-writing` | SKILL.md → 맥락 파악 |

## 설계 원칙

1. **P1 — 정확도를 위한 데이터 정제**: AI에게 전달하기 전 Python 등으로 노이즈 제거. 전처리·후처리 명시.
2. **P2 — 전문성 기반 위임 구조**: 전문 에이전트에게 위임하여 품질 극대화. Orchestrator는 조율만.
3. **P3 — 이미지/리소스 정확성**: 정확한 다운로드 경로 명시. placeholder 누락 불가.
4. **P4 — 질문 설계 규칙**: 최대 4개 질문, 각 3개 선택지. 모호함 없으면 질문 없이 진행.

## 언어 및 스타일 규칙

- **콘텐츠**: 한국어
- **기술 용어**: 영어 유지 (e.g., SOT, Agent Team, Hooks)
- **시각화**: Mermaid 다이어그램 선호
- **깊이**: 간략 요약보다 포괄적·데이터 기반 서술 선호

## 스킬 개발 규칙

새로운 스킬을 만들거나 기존 스킬을 수정할 때:

1. **절대 기준 3개를 반드시 포함**한다 — 해당 도메인에 맞게 맥락화하여 적용.
2. **파일 간 역할 분담**을 명확히 한다 — SKILL.md(WHY), references/(WHAT/HOW/VERIFY).
3. **절대 기준 간 충돌 시나리오**를 구체적으로 명시한다 — 추상적 규칙이 아닌 실전 판단 기준.
4. 수정 후 반드시 **절대 기준 관점에서 성찰**한다 — 문구만 넣지 않고 기존 내용과 충돌 여부를 점검.
