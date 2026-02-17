# Workflow Template

workflow.md 파일의 표준 구조.

## 기본 템플릿

```markdown
# [워크플로우 이름]

[워크플로우 목적 한 줄 설명]

## Overview

- **Input**: [입력 데이터/트리거]
- **Output**: [최종 산출물]
- **Frequency**: [실행 주기 - daily/weekly/on-demand 등]
- **Autopilot**: [disabled|enabled] — 사람 개입 지점 자동 승인 모드 (기본값: disabled)

---

## Research

### 1. [단계명]
- **Pre-processing**: [Python script 등으로 데이터 정제 — 생략 가능]
- **Agent**: `@[agent-name]`
- **Task**: [수행 작업]
- **Output**: [단계 산출물]
- **Post-processing**: [산출물 정제 — 생략 가능]

### 2. [단계명]
- **Pre-processing**: [데이터 전처리]
- **Agent**: `@[agent-name]`
- **Task**: [수행 작업]
- **Output**: [단계 산출물]

### 3. (human) [검토 단계명]
- **Action**: [사람이 수행할 작업]
- **Command**: `/[command-name]`

---

## Planning

### 4. [단계명]
- **Pre-processing**: [데이터 전처리]
- **Agent**: `@[agent-name]`
- **Task**: [수행 작업]
- **Output**: [단계 산출물]
- **Post-processing**: [산출물 정제]

### 5. [단계명]
- **Agent**: `@[agent-name]`
- **Task**: [수행 작업]
- **Output**: [단계 산출물]

### 6. (human) [검토 단계명]
- **Action**: [사람이 수행할 작업]
- **Command**: `/[command-name]`

---

## Implementation

### 7. [단계명]
- **Pre-processing**: [데이터 전처리]
- **Agent**: `@[agent-name]`
- **Task**: [수행 작업]
- **Output**: [최종 산출물]

---

## Claude Code Configuration

### Sub-agents

```yaml
# .claude/agents/[agent-name].md frontmatter 형식
---
name: [고유 식별자]
description: "[자동 위임 트리거 설명]"
model: [opus|sonnet|haiku]        # 품질 기준으로 선택 (절대 기준 1)
tools: [허용 도구 — 쉼표 구분]
disallowedTools: [차단 도구]       # 선택적
permissionMode: [default|plan|dontAsk]
maxTurns: [최대 턴 수]
memory: [user|project|local]      # C-3: 스코프 정의 아래 참조
skills: [주입할 스킬 목록]         # 선택적
mcpServers: [사용 가능 MCP]       # 선택적
---

[에이전트 시스템 프롬프트]
```

> **모델 선택 기준 (절대 기준 1)**: opus = 최고 품질 핵심 작업, sonnet = 안정적 반복 작업, haiku = 단순 보조 작업. "비용이 싸서"가 아니라 "품질이 충분한가"로 판단한다.

#### Sub-agent Memory Scope 정의 (C-3)

| Scope | 접근 범위 | SOT | 부모 세션 컨텍스트 | Knowledge Index | 용도 |
|-------|----------|-----|------------------|-----------------|------|
| `user` | 모든 프로젝트의 에이전트 | read-only | 없음 | 가능 | 글로벌 유틸리티 에이전트 |
| `project` | 현재 프로젝트 내 에이전트 | read-only | Task prompt로 전달 | 가능 | 프로젝트 전문 에이전트 (기본값) |
| `local` | 단일 에이전트 세션 | read-only | Task prompt로 전달 | 없음 | 일회성 분석/처리 작업 |

> **Context Preservation과의 관계**: `project` 스코프 에이전트는 부모의 `latest.md` 경로를 Task prompt에 포함하면 세션 컨텍스트를 읽을 수 있다. `local` 스코프는 prompt에 전달된 내용만 사용하며, 세션 간 기억이 없다.

### Agent Team (병렬 협업이 필요한 경우)

```markdown
### [N]. (team) [단계명]
- **Team**: `[team-name]`
- **Tasks**:
  - `@[teammate-1]` ([model]): [작업 설명]
  - `@[teammate-2]` ([model]): [작업 설명]
- **Join**: [합류 조건 — 예: 모든 팀원 완료 후 다음 단계]
- **SOT 쓰기**: Team Lead만 `state.yaml` 갱신 (팀원은 산출물 파일만 생성)
```

> **선택 기준**: Agent Team은 "빠르니까"가 아니라, 독립 전문가 병렬 작업이나 다관점 교차 검증이 **품질을 높이는 경우**에만 사용한다. 상세: `references/claude-code-patterns.md §2`

**Team 생명주기 패턴:**

| 패턴 | 설명 | SOT 정합성 | 사용 시점 |
|------|------|-----------|----------|
| **Step-scoped** (기본) | 단계 시작 시 TeamCreate → 단계 완료 시 TeamDelete | 간단 — active_team 1개만 추적 | 대부분의 경우 |
| **Multi-step** | 여러 단계에 걸쳐 팀 유지 | 복잡 — 팀원 교체/추가 추적 필요 | 동일 전문가 그룹이 연속 단계를 수행해야 할 때 |

> **기본값은 Step-scoped이다.** Multi-step은 품질 향상이 명확할 때만 사용하고, 사유를 SOT 섹션의 "품질 우선 조정"에 기술한다.

### SOT (상태 관리)
- **SOT 파일**: `.claude/state.yaml`
- **쓰기 권한**: [Orchestrator 또는 Team Lead — 단일 쓰기 지점]
- **에이전트 접근**: [읽기 전용 — 산출물 파일만 생성, SOT 직접 수정 금지]
- **품질 우선 조정**: [SOT 기본 패턴이 품질 병목을 일으키는 경우(예: 팀원이 stale data로 작업), 팀원 간 산출물 직접 참조 등 구조 조정 사유를 여기에 기술. 해당 없으면 "기본 패턴 적용" 기재. 상세: `references/claude-code-patterns.md §상태 관리`]

#### Agent Team 사용 시 SOT 스키마 (active_team)

Agent Team `(team)` 단계가 포함된 워크플로우는 SOT에 `active_team` 필드를 추가한다:

```yaml
# state.yaml — Agent Team 활성 시 추가 필드
workflow:
  # ... 기존 필드 (name, current_step, status, outputs, autopilot) ...
  active_team:
    name: "[team-name]"
    status: "partial"               # partial | all_completed
    tasks_completed: ["task-1"]
    tasks_pending: ["task-2", "task-3"]
    completed_summaries:            # RLM Layer 2 — 세션 복원 시 팀 작업 맥락 보존
      task-1:
        agent: "@[agent-name]"
        model: "[opus|sonnet|haiku]"
        output: "[산출물 경로]"
        summary: "[작업 요약 — 1-2문장]"
  completed_teams: []               # 완료된 팀 이력 (감사 추적)
```

**SOT 갱신 시점 (Team Lead만 수행):**
1. `TeamCreate` 직후 → `active_team` 기록
2. 각 Teammate 완료 시 (즉시) → `tasks_completed` 추가, `completed_summaries` 기록
3. 모든 Task 완료 시 (즉시) → `outputs` 기록, `current_step` +1
4. `TeamDelete` 직후 → `active_team` → `completed_teams` 이동

> **상세 프로토콜**: `references/claude-code-patterns.md §SOT 갱신 프로토콜`

### Task Management

```markdown
# 워크플로우 내 Task 설계 (Agent Team 사용 시)
#### Task [N]: [작업명]
- **subject**: "[짧은 제목]"
- **description**: "[수행 내용 + 산출물 경로]"
- **activeForm**: "[진행 중 표시 문구]"
- **owner**: `@[agent-name]`
- **blocks**: [이 Task에 의존하는 다른 Task 목록]
- **blockedBy**: [이 Task가 의존하는 다른 Task 목록]
```

> **주의**: Task List(`~/.claude/tasks/`)는 작업 할당/추적 도구이지 SOT가 아니다. 워크플로우 상태는 반드시 SOT(`state.yaml`)에서 관리한다.

### Hooks

```json
// .claude/settings.json 형식
{
  "hooks": {
    "[이벤트명]": [
      {
        "matcher": "[대상 도구 — 예: Edit|Write]",  // 선택적
        "hooks": [
          {
            "type": "command",                      // command | prompt | agent
            "command": "[실행할 명령]",
            "timeout": 30                            // 초 단위
          }
        ]
      }
    ]
  }
}
```

**Exit Code 규칙**: `0` = 통과, `2` = 차단 (stderr → Claude에 피드백), 기타 = 논블로킹 에러
**상세 패턴**: `references/claude-code-patterns.md §3. Hooks`

### Setup Hooks (선택적 — 인프라 검증이 필요한 경우)

워크플로우가 Hook 스크립트, 외부 의존성, 런타임 디렉터리 등 인프라에 의존하는 경우 포함한다.

```json
// .claude/settings.json (Setup 이벤트)
{
  "hooks": {
    "Setup": [
      {
        "matcher": "init",
        "hooks": [{
          "type": "command",
          "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/[setup_script].py",
          "timeout": 30
        }]
      }
    ]
  }
}
```

| 포함 기준 | 제외 기준 |
|----------|----------|
| Hook 스크립트 3개 이상 | Hook 없는 단순 워크플로우 |
| 외부 의존성 (PyYAML, npm 등) | 표준 라이브러리만 사용 |
| 런타임 디렉터리 사전 생성 필요 | 별도 인프라 불필요 |
| CI/CD 파이프라인 통합 (`--init-only`) | 로컬 전용 워크플로우 |

> **SOT 비접근**: Setup Hook은 인프라 계층에서 작동하며 SOT(`state.yaml`)에 접근하지 않는다.
> **상세 패턴**: `references/claude-code-patterns.md §3-1. Setup Hooks`

### Slash Commands

```markdown
# .claude/commands/[command-name].md 형식
---
description: "[명령어 설명]"
---

[명령어 실행 시 Claude에 전달되는 프롬프트]
$ARGUMENTS  ← 사용자 입력 파라미터
```

### Required Skills
[필요 스킬 목록 — `.claude/skills/[name]/SKILL.md`]

### MCP Servers
[외부 연동 서버 — `.mcp.json` 또는 `.claude/settings.json`에 정의]

### Error Handling

```yaml
error_handling:
  on_agent_failure:
    action: retry_with_feedback
    max_attempts: 3
    escalation: human    # 3회 초과 시 사용자에게 에스컬레이션

  on_validation_failure:
    action: retry_or_rollback
    retry_with_feedback: true
    rollback_after: 3    # 3회 실패 후 이전 단계로 롤백

  on_hook_failure:
    action: log_and_continue   # Hook 실패는 워크플로우를 차단하지 않음

  on_context_overflow:
    action: save_and_recover   # Context Preservation System 자동 적용

  on_teammate_failure:              # Agent Team 사용 시
    attempt_1: retry_same_agent     # SendMessage로 피드백 → 같은 Teammate 재작업
    attempt_2: replace_with_upgrade # Teammate shutdown → 새 Teammate (상위 모델)
    attempt_3: human_escalation     # AskUserQuestion으로 사용자 판단 요청
```

> **상세 패턴**: `references/claude-code-patterns.md §에러 처리`

### Autopilot Logs (Autopilot 모드 사용 시)

```yaml
autopilot_logging:
  log_directory: "autopilot-logs/"
  log_format: "step-{N}-decision.md"
  required_fields:
    - step_number
    - checkpoint_type        # slash_command | ask_user_question
    - decision
    - rationale              # 절대 기준 1 기반
    - timestamp
  template: "references/autopilot-decision-template.md"
```

**Decision Log 예시** (`autopilot-logs/step-3-decision.md`):

```markdown
# Decision Log — Step 3

- **Step**: 3
- **Checkpoint Type**: (human) — 인사이트 검토 및 선정
- **Decision**: 상위 5개 인사이트 전체 선정 (포괄성 극대화)
- **Rationale**: 절대 기준 1 — 품질 극대화를 위해 인사이트를 제외하지 않고
  모두 포함하여 Planning Phase에서 우선순위를 정하는 방식 선택.
  특정 인사이트를 미리 제외하면 정보 손실 위험.
- **Timestamp**: 2026-02-16 14:30:00
- **Alternatives Considered**:
  - 상위 3개만 선정 → 정보 손실 위험으로 기각
  - 카테고리별 1개씩 선정 → 카테고리 분류가 불완전하여 기각
```

> **런타임 보조**: Stop hook(`generate_context_summary.py`)이 Decision Log 누락을 감지하여 안전망으로 자동 생성한다. Claude가 직접 생성한 로그가 항상 우선.

```

## 표기 규칙

| 표기 | 의미 |
|-----|------|
| `(human)` | 사람의 개입/검토 필요 |
| `(team)` | Agent Team 병렬 실행 구간 |
| `(hook)` | 자동 검증/품질 게이트 |
| `@agent-name` | Sub-agent 호출 |
| `/command-name` | Slash command 실행 |
| `[skill-name]` | Skill 참조 |

## 예시: 블로그 컨텐츠 생성 워크플로우

```markdown
# Blog Content Pipeline

블로그 컨텐츠를 체계적으로 리서치, 기획, 작성하는 워크플로우.

## Overview

- **Input**: 컨텐츠 채널 (RSS, Newsletter, SNS)
- **Output**: 퍼블리싱 준비된 블로그 글
- **Frequency**: Weekly
- **Autopilot**: disabled

---

## Research

### 1. 리소스 수집
- **Agent**: `@content-collector`
- **Task**: 정해진 채널에서 최신 컨텐츠 수집
- **Output**: `raw-contents.md`

### 2. 인사이트 추출
- **Agent**: `@insight-extractor`
- **Task**: 수집된 컨텐츠에서 핵심 인사이트 도출
- **Output**: `insights-list.md`

### 3. (human) 인사이트 검토 및 선정
- **Action**: 글로 작성할 인사이트 선택
- **Command**: `/review-insights`

---

## Planning

### 4. 심층 리서치
- **Agent**: `@deep-researcher`
- **Task**: 선정 주제에 대한 전문 자료/트렌드 조사
- **Output**: `research-notes.md`

### 5. 개요 작성
- **Agent**: `@outline-writer`
- **Task**: 조사 내용 기반 글 개요 작성
- **Output**: `article-outlines.md`

### 6. (human) 개요 검토 및 피드백
- **Action**: 개요 검토 후 수정 방향 제시
- **Command**: `/review-outline`

---

## Implementation

### 7. 최종본 작성
- **Agent**: `@article-writer`
- **Task**: 피드백 반영하여 최종 글 작성
- **Output**: `final-article.md`

---

## Claude Code Configuration

### Sub-agents

\`\`\`yaml
agents:
  content-collector:
    description: "RSS/Newsletter에서 컨텐츠 수집"
    tools: [web-fetch, rss-reader]

  insight-extractor:
    description: "컨텐츠에서 핵심 인사이트 추출"
    prompt: "다음 컨텐츠에서 블로그 주제가 될 인사이트를 추출하세요..."

  deep-researcher:
    description: "주제에 대한 심층 조사"
    tools: [web-search, scholar-search]

  outline-writer:
    description: "글 개요 작성"
    skills: [writing-style]

  article-writer:
    description: "최종 글 작성"
    skills: [writing-style, seo-optimization]
\`\`\`

### Slash Commands

\`\`\`yaml
commands:
  /review-insights:
    description: "추출된 인사이트 목록 표시 및 선택 대기"

  /review-outline:
    description: "작성된 개요 표시 및 피드백 입력 대기"

  /run-pipeline:
    description: "전체 워크플로우 실행"
\`\`\`

### Agent Team (Research Phase 병렬화)

Step 1~2를 병렬로 수행할 경우:
- Team name: `blog-research`
- `@content-collector`: RSS/Newsletter 수집 → `raw-contents.md` 생성
- `@trend-analyzer`: 트렌드 데이터 분석 → `trend-data.md` 생성
- **Join**: Team Lead가 두 팀원의 산출물을 수신 → `state.yaml`에 상태 병합 → Step 3으로
- **SOT 쓰기**: Team Lead만 `state.yaml` 갱신 (팀원은 산출물 파일만 생성)

### Hooks

\`\`\`json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [{
          "type": "command",
          "command": "prettier --write \"$(jq -r '.tool_input.file_path')\" 2>/dev/null || true"
        }]
      }
    ],
    "TaskCompleted": [
      {
        "hooks": [{
          "type": "prompt",
          "prompt": "산출물의 출처가 모두 포함되어 있는지 검증하세요.",
          "model": "haiku"
        }]
      }
    ]
  }
}
\`\`\`

### Required Skills
- writing-style
- seo-optimization
- content-formatting

### MCP Servers
- rss-reader-mcp
- notion-mcp (optional)
```
