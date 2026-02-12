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
[에이전트 정의 — .claude/agents/*.md 파일로 생성]

### Agent Team (병렬 협업이 필요한 경우)
[팀 구성 — 독립 세션 간 병렬 작업]

### SOT (상태 관리)
- **SOT 파일**: `.claude/state.yaml`
- **쓰기 권한**: [Orchestrator 또는 Team Lead — 단일 쓰기 지점]
- **에이전트 접근**: [읽기 전용 — 산출물 파일만 생성, SOT 직접 수정 금지]
- **품질 우선 조정**: [SOT 기본 패턴이 품질 병목을 일으키는 경우, 팀원 간 산출물 직접 참조 등 구조 조정 사유를 여기에 기술. 해당 없으면 "기본 패턴 적용" 기재]

### Hooks
[자동화 트리거 — .claude/settings.json에 정의]

### Slash Commands
[커맨드 정의 — .claude/commands/*.md 파일로 생성]

### Required Skills
[필요 스킬 목록]

### MCP Servers
[외부 연동 서버 목록]
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
