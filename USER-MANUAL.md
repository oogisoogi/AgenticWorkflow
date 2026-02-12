# AgenticWorkflow 사용자 매뉴얼

이 문서는 AgenticWorkflow 프로젝트를 사용하여 워크플로우를 설계하고 구현하는 전체 과정을 안내합니다.

---

## 1. 시작하기

### 1.1 사전 준비

| 항목 | 필수 여부 | 설명 |
|------|----------|------|
| [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) | 필수 | `npm install -g @anthropic-ai/claude-code` |
| GitHub 계정 | 권장 | 저장소 clone 및 협업 |
| Python 3.10+ | 선택 | 데이터 전처리/후처리 스크립트 실행 시 |
| Node.js 18+ | 선택 | MCP Server 연동 시 |

### 1.2 설치

```bash
git clone https://github.com/idoforgod/AgenticWorkflow.git
cd AgenticWorkflow
```

### 1.3 프로젝트 열기

```bash
claude          # Claude Code 실행 (AgenticWorkflow 디렉터리에서)
```

Claude Code가 실행되면 `CLAUDE.md`를 자동으로 읽고, 프로젝트의 절대 기준과 설계 원칙을 적용합니다.

---

## 2. 전체 흐름

```
사용자의 아이디어 또는 설명 문서
        ↓
┌─────────────────────────────────┐
│ Phase 1: 워크플로우 설계          │
│  workflow-generator 스킬 사용     │
│  → workflow.md 생성 (설계도)      │
└─────────────────────────────────┘
        ↓
┌─────────────────────────────────┐
│ Phase 2: 워크플로우 구현          │
│  workflow.md 기반으로 실제 구현    │
│  → 에이전트, 스크립트, 자동화 설정  │
│  → 실제 동작하는 시스템 (최종 목표) │
└─────────────────────────────────┘
```

---

## 3. Phase 1: 워크플로우 설계

### 3.1 워크플로우 생성 요청

Claude Code에서 다음과 같이 요청합니다:

```
워크플로우 만들어줘
```

또는:

```
자동화 파이프라인 설계해줘
```

`workflow-generator` 스킬이 자동으로 활성화됩니다.

### 3.2 두 가지 케이스

#### Case 1: 아이디어만 있는 경우

설명 문서 없이 아이디어만 있을 때. AI가 대화형 질문으로 요구사항을 수집합니다.

```
사용자: "블로그 컨텐츠를 자동으로 리서치하고 작성하는 워크플로우 만들어줘"

AI 질문 예시:
1. "어떤 결과물(output)을 만들고 싶으신가요?"
2. "주요 입력(input) 소스는 무엇인가요?"
3. "어느 단계에서 사람의 검토가 필요한가요?"
```

#### Case 2: 설명 문서가 있는 경우

PDF 등 구체적인 설명 문서를 첨부할 때. AI가 문서를 먼저 분석한 후 확인 질문을 합니다.

```
사용자: "이 PDF를 기반으로 워크플로우 만들어줘" + [파일 첨부]

AI 동작:
1. 문서 심층 분석 → 목적, 단계, 입출력, 제약 조건 추출
2. 분석 결과 요약 제시
3. 확인 질문 (짧게)
4. workflow.md 생성
```

### 3.3 생성되는 workflow.md 구조

모든 워크플로우는 3단계로 구성됩니다:

```markdown
# [워크플로우 이름]

## Overview
- Input: [입력 데이터]
- Output: [최종 산출물]
- Frequency: [실행 주기]

## Research
### 1. [리서치 단계]
- Pre-processing: [데이터 전처리]
- Agent: @[agent-name]
- Task: [수행 작업]
- Output: [산출물]
- Post-processing: [산출물 정제]

## Planning
### 2. [기획 단계]
...
### 3. (human) [검토 단계]
- Action: [사람이 수행할 작업]

## Implementation
### 4. [실행 단계]
...

## Claude Code Configuration
### Sub-agents / Agent Team / Hooks / Slash Commands / Skills / MCP Servers
```

### 3.4 워크플로우 표기법

| 표기 | 의미 |
|-----|------|
| `(human)` | 사람의 개입/검토 필요 |
| `(team)` | Agent Team 병렬 실행 구간 |
| `(hook)` | 자동 검증/품질 게이트 |
| `@agent-name` | Sub-agent 호출 |
| `/command-name` | Slash command 실행 |

---

## 4. Phase 2: 워크플로우 구현

workflow.md가 생성되면, 그 안에 정의된 구성요소를 실제로 만듭니다.

### 4.1 구현해야 할 구성요소

| workflow.md에 정의된 것 | 실제로 만들 파일 | 위치 |
|----------------------|---------------|------|
| Sub-agents | `.md` 파일 | `.claude/agents/` |
| Slash commands | `.md` 파일 | `.claude/commands/` |
| Hooks | JSON 설정 | `.claude/settings.json` |
| 전처리/후처리 스크립트 | Python/Bash | `scripts/` |
| SOT 파일 | YAML/JSON | `.claude/state.yaml` |
| MCP Server 설정 | JSON | `.mcp.json` |

### 4.2 Sub-agent 만들기

workflow.md에 `@researcher`가 정의되어 있다면:

```markdown
# .claude/agents/researcher.md
---
name: researcher
description: 웹 검색 및 자료 조사 전문
model: sonnet
tools: Read, Glob, Grep, WebSearch, WebFetch
maxTurns: 30
---

당신은 리서치 전문가입니다.
주어진 주제에 대해 체계적으로 자료를 수집하고 요약합니다.

## 작업 원칙
- 모든 정보에 출처(URL) 필수
- 핵심 인사이트를 구조화된 형식으로 정리
```

**모델 선택 기준:**

| 모델 | 적합한 작업 |
|-----|-----------|
| `opus` | 복잡한 분석, 연구, 작문 — 최고 품질이 필요한 핵심 작업 |
| `sonnet` | 수집, 스캐닝, 구조화 — 안정적 품질의 반복 작업 |
| `haiku` | 상태 확인, 단순 판단 — 복잡도가 낮은 보조 작업 |

### 4.3 Agent Team 설정 (병렬 협업)

workflow.md에 `(team)` 구간이 있다면:

```json
// .claude/settings.json — Agent Team 활성화
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

**팀 작업 흐름:**
```
Team Lead (조율 + SOT 쓰기)
  ├→ Teammate A → 산출물 파일 생성 (output-a.md)
  ├→ Teammate B → 산출물 파일 생성 (output-b.md)
  └→ Team Lead → state.yaml에 상태 병합 → 다음 단계
```

### 4.4 Hooks 설정 (자동화 게이트)

workflow.md에 `(hook)` 구간이 있다면:

```json
// .claude/settings.json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{
          "type": "command",
          "command": "prettier --write \"$(jq -r '.tool_input.file_path')\" 2>/dev/null || true",
          "statusMessage": "자동 포맷팅 중..."
        }]
      }
    ],
    "TaskCompleted": [
      {
        "hooks": [{
          "type": "agent",
          "prompt": "완료된 태스크의 산출물 품질을 검증하세요.",
          "timeout": 60
        }]
      }
    ]
  }
}
```

**Hook Exit Code:**

| 코드 | 동작 |
|------|------|
| `0` | 통과 |
| `2` | 차단 — 에이전트에 피드백 전달, 재작업 |

### 4.5 Slash Commands 만들기

workflow.md에 사용자 개입 지점이 있다면:

```markdown
# .claude/commands/review-output.md
---
description: "산출물 검토 및 승인/반려"
---

현재 단계의 산출물을 표시하고 사용자의 승인/반려를 대기합니다.
- 승인 시: 다음 단계로 자동 진행
- 반려 시: 피드백을 에이전트에 전달하여 재작업
```

### 4.6 SOT 파일 초기화

```yaml
# .claude/state.yaml
workflow:
  name: "my-workflow"
  current_step: 1
  status: "ready"
  outputs: {}
```

**SOT 규칙:**
- 쓰기: Orchestrator 또는 Team Lead만
- 읽기: 모든 에이전트 가능
- 팀원: 산출물 파일만 생성, SOT 직접 수정 금지

---

## 5. 실행 패턴

### 5.1 순차 파이프라인 (기본)

```
@agent-1 → @agent-2 → (human) 검토 → @agent-3
```

하나의 전문가가 깊은 맥락을 유지하며 일관되게 처리할 때.

### 5.2 병렬 분기 (Agent Team)

```
           ┌→ @teammate-a ─┐
Team Lead ─┤                ├→ (human) 검토 → @agent-merge
           └→ @teammate-b ─┘
```

서로 다른 전문 영역을 각각 최고 수준으로 처리할 때.

### 5.3 자동 검증 게이트 (Hook)

```
@agent-1 → [Hook: 품질 검증] → @agent-2
                ↓ 실패 시
           피드백 전달 → 재작업
```

코드 품질, 보안 검증, 표준 준수가 중요할 때.

---

## 6. 스킬 사용

### 6.1 workflow-generator

**트리거 키워드:** 워크플로우 만들어줘, 자동화 파이프라인 설계, 작업 흐름 정의

**상세:** `.claude/skills/workflow-generator/SKILL.md` 참조

### 6.2 doctoral-writing

**트리거 키워드:** 논문 스타일로 써줘, 학술적 글쓰기, 논문 문장 다듬기

**용도:**
- 학위논문 챕터 검토 및 작성
- 학술지 투고 논문 교정
- 연구보고서, 학술 발표문 작성

**상세:** `.claude/skills/doctoral-writing/SKILL.md` 참조

---

## 7. 프롬프트 자료

| 파일 | 용도 | 사용법 |
|------|------|--------|
| `prompt/crystalize-prompt.md` | 긴 AI 에이전트 지침을 핵심만 남겨 압축 | 프롬프트가 너무 길 때 압축 기법 적용 |
| `prompt/distill-partner.md` | 에센스 추출 및 최적화 인터뷰 | 작업 계획이 복잡할 때 핵심/불필요/자동화 분류 |
| `prompt/crawling-skill-sample.md` | 네이버 뉴스 크롤링 차단 방어 스킬 샘플 | 스킬 파일 작성법 참고용 |

---

## 8. 이론적 기반

`coding-resource/recursive language models.pdf`

장기기억(long-term memory) 구현에 필수적인 이론을 담은 논문입니다. 에이전트가 세션을 넘어 지식을 축적하고 활용하는 메커니즘의 이론적 토대입니다.

---

## 9. 다른 AI 도구에서 사용

이 프로젝트는 Claude Code 외의 AI 코딩 도구에서도 동일한 원칙으로 작동하도록 설계되었습니다.

| 도구 | 참조 파일 |
|------|----------|
| Claude Code | `CLAUDE.md` (도구 고유 기능에 맞춘 구현 매핑) |
| Cursor, Copilot, Codex, Windsurf 등 | `AGENTS.md` (모델 무관 공통 지시서) |

두 파일의 절대 기준과 설계 원칙은 동일합니다.

---

## 10. 전체 요약: 워크플로우 설계 → 구현 체크리스트

### Phase 1: 설계

- [ ] 아이디어 또는 설명 문서 준비
- [ ] `workflow-generator` 스킬로 `workflow.md` 생성
- [ ] 생성된 워크플로우 검토 — 단계, 에이전트, 사람 개입 지점 확인

### Phase 2: 구현

- [ ] Sub-agent `.md` 파일 생성 (`.claude/agents/`)
- [ ] Slash command `.md` 파일 생성 (`.claude/commands/`)
- [ ] Hooks 설정 (`.claude/settings.json`)
- [ ] 전처리/후처리 스크립트 작성 (`scripts/`)
- [ ] SOT 파일 초기화 (`.claude/state.yaml`)
- [ ] MCP Server 연동 설정 (`.mcp.json`, 필요 시)
- [ ] Agent Team 설정 (병렬 협업 필요 시)

### 검증

- [ ] 워크플로우 전체 실행 테스트
- [ ] 각 단계의 산출물 품질 확인
- [ ] SOT 파일 일관성 확인
- [ ] Hook 게이트 정상 동작 확인
