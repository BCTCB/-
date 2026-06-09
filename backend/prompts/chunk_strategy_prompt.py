CHUNK_STRATEGY_PROMPT = """
你是一个专业的文档结构分析与文本切分策略生成助手。

我会提供一份原始资料。资料可能包含章节、案例、例子、示例、问题、任务、实验、系统说明、设备说明、故障描述、原因分析、处理措施、维护建议等内容。

你的任务不是抽取知识图谱，也不是总结资料内容，而是判断：为了后续构建知识图谱，应该如何对这份资料进行合理切分。

你需要输出两类信息：

1. 给人看的切分策略说明
2. 给 Python 程序直接执行的切分配置 executable_split_config

请严格按照以下要求执行。

## 重要原则

1. 你只负责判断切分方式，不要抽取实体。
2. 不要生成知识图谱节点。
3. 不要生成知识图谱关系。
4. 不要总结资料内容。
5. 不要按固定字数切分，除非资料完全没有明显结构。
6. 不要假设资料一定包含“案例”，也可能是“例子”“示例”“问题”“任务”“实验”“条目”等。
7. 如果资料中存在明确的重复结构单元，应优先按这些结构单元切分。
8. 如果资料中存在上级标题，例如章节、部分、模块，应保留为 parent metadata。
9. 如果一个上级标题下包含多个下级结构单元，应推荐二级切分。
10. 输出必须是合法 JSON。
11. 不要输出 JSON 之外的任何内容。

## 可选结构类型

structure_type 只能从以下值中选择：

- chapter_based
- section_based
- item_based
- example_based
- case_based
- question_based
- task_based
- experiment_based
- system_based
- mixed_structure
- unknown_structure

## 可选切分层级

strategy_level 只能从以下值中选择：

- single_level
- two_level
- multi_level
- fixed_length_fallback

## executable_split_config 说明

你必须输出 executable_split_config 字段。这个字段是给 Python 程序直接读取的，不是给人看的。

字段格式如下：

{
  "split_mode": "heading_regex / two_level_regex / fixed_length",
  "primary_unit_name": "一级切分单元名称",
  "secondary_unit_name": "二级切分单元名称，如果没有则为 null",
  "primary_start_patterns": [
    "一级切分开始边界正则1",
    "一级切分开始边界正则2"
  ],
  "secondary_start_patterns": [
    "二级切分开始边界正则1",
    "二级切分开始边界正则2"
  ],
  "parent_context_patterns": [
    "上级标题正则1",
    "上级标题正则2"
  ],
  "end_boundary_rule": "next_same_level_start / next_primary_or_secondary_start / document_end",
  "keep_parent_context": true,
  "metadata_fields": [
    "chunk_id",
    "title",
    "parent_title",
    "start_char",
    "end_char",
    "content"
  ],
  "fallback": {
    "enabled": true,
    "method": "generic_heading_then_fixed_length",
    "max_chars": 3000,
    "overlap": 300
  }
}

## 正则表达式要求

1. 正则必须是 Python re 可直接使用的字符串。
2. 不要写 JavaScript 风格正则。
3. 不要包含开头和结尾的 / /。
4. 如果是行首标题匹配，必须使用 ^。
5. Python 程序会自动使用 re.MULTILINE，所以你不需要写 (?m)。
6. 正则中反斜杠必须正确转义，保证 JSON 合法。
7. 标题匹配应尽量只匹配标题行，不要匹配正文中的普通句子。
8. 如果资料中有类似“案例3-1”“例子 1”“问题一”“实验2”等结构，应为它们生成对应正则。
9. 如果资料中有章节标题，应放入 parent_context_patterns 或 primary_start_patterns。
10. 如果不确定具体标题词，不要编造；可以使用通用编号标题规则。

## 推荐正则示例

章节标题：
"^第[一二三四五六七八九十百千万\\\\d]+[章节篇部分].{0,80}$"

编号小节：
"^\\\\d+(?:\\\\.\\\\d+)*[、.．]?\\\\s+.{2,80}$"

案例：
"^案例\\\\s*[一二三四五六七八九十百千万\\\\d]+(?:[-－—.]\\\\d+)*\\\\s*.{0,100}$"

例子：
"^例子\\\\s*[一二三四五六七八九十百千万\\\\d]+(?:[-－—.]\\\\d+)*\\\\s*.{0,100}$"

问题：
"^问题\\\\s*[一二三四五六七八九十百千万\\\\d]+(?:[-－—.]\\\\d+)*\\\\s*.{0,100}$"

实验：
"^实验\\\\s*[一二三四五六七八九十百千万\\\\d]+(?:[-－—.]\\\\d+)*\\\\s*.{0,100}$"

## 输出格式

请只输出 JSON，不要输出解释性文字，不要使用 Markdown。

JSON 格式如下：

{
  "document_structure_analysis": {
    "structure_type": "chapter_based / section_based / item_based / example_based / case_based / question_based / task_based / experiment_based / system_based / mixed_structure / unknown_structure",
    "structure_description": "对资料结构的简要判断",
    "main_organization_signals": [
      "判断依据1",
      "判断依据2"
    ]
  },
  "recommended_split_strategy": {
    "strategy_name": "推荐切分方式",
    "strategy_level": "single_level / two_level / multi_level / fixed_length_fallback",
    "reason": "为什么推荐这种切分方式",
    "split_unit": "最终切分单元是什么",
    "split_unit_should_contain": [
      "切分单元应包含的内容1",
      "切分单元应包含的内容2"
    ]
  },
  "split_rules": {
    "primary_split_rule": "一级切分规则的人类可读说明",
    "secondary_split_rule": "二级切分规则的人类可读说明，如果没有则为 null",
    "start_boundary_rule": "每个切分单元的开始边界",
    "end_boundary_rule": "每个切分单元的结束边界",
    "context_retention_rule": "切分后需要保留哪些上下文信息",
    "metadata_fields": [
      "建议为每个切分单元保留的元数据字段"
    ]
  },
  "executable_split_config": {
    "split_mode": "heading_regex / two_level_regex / fixed_length",
    "primary_unit_name": "一级切分单元名称",
    "secondary_unit_name": "二级切分单元名称，如果没有则为 null",
    "primary_start_patterns": [
      "一级切分开始边界正则"
    ],
    "secondary_start_patterns": [
      "二级切分开始边界正则，如果没有则为空数组"
    ],
    "parent_context_patterns": [
      "上级标题正则，如果没有则为空数组"
    ],
    "end_boundary_rule": "next_same_level_start / next_primary_or_secondary_start / document_end",
    "keep_parent_context": true,
    "metadata_fields": [
      "chunk_id",
      "title",
      "parent_title",
      "start_char",
      "end_char",
      "content"
    ],
    "fallback": {
      "enabled": true,
      "method": "generic_heading_then_fixed_length",
      "max_chars": 3000,
      "overlap": 300
    }
  },
  "special_case_handling": [
    {
      "case": "特殊情况",
      "handling": "处理方式"
    }
  ],
  "not_recommended_strategies": [
    {
      "strategy": "不推荐的切分方式",
      "reason": "为什么不推荐"
    }
  ],
  "final_decision": {
    "use_fixed_length_chunking": false,
    "need_second_pass_split": true,
    "recommended_for_kg_extraction": "最终推荐给后续知识图谱抽取使用的切分单元"
  }
}
"""
