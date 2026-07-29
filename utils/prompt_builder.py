from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(relative_path: str) -> str:

    with open(PROMPT_DIR / relative_path, "r", encoding="utf-8") as file:
        return file.read().strip()


def format_helper_methods(helper_methods: dict) -> str:

    if not isinstance(helper_methods, dict) or not helper_methods:
        return ""

    lines = [
        "### 2. Helper Methods",
        ""
    ]

    for method_name, method_code in helper_methods.items():

        lines.append(f"Method: {method_name}")
        lines.append("")
        lines.append(method_code.strip())
        lines.append("")
        lines.append("-" * 40)
        lines.append("")

    return "\n".join(lines).strip()


def format_production_code(code_under_test: dict) -> str:

    if not isinstance(code_under_test, dict) or not code_under_test:
        return ""

    lines = [
        "### 4. Production Code",
        ""
    ]

    for class_name, methods in code_under_test.items():

        lines.append(f"Class: {class_name}")
        lines.append("")

        if isinstance(methods, dict):

            for method_name, method_code in methods.items():

                lines.append(f"Method: {method_name}")
                lines.append("")
                lines.append(method_code.strip())
                lines.append("")
                lines.append("-" * 40)
                lines.append("")

    return "\n".join(lines).strip()


def build_input_section(
    sample: dict,
    include_context: bool = True
) -> str:

    sections = [
        "## Input"
    ]

    test_code = sample.get("test_code", "")

    if test_code:

        sections.append(
            "### 1. Test Code\n\n"
            + test_code.strip()
        )

    if include_context:

        helper_section = format_helper_methods(
            sample.get("helper_methods_json")
        )

        if helper_section:
            sections.append(helper_section)

        failure_log = sample.get("failure_log", "")

        if failure_log:

            sections.append(
                "### 3. Failure Log\n\n"
                + failure_log.strip()
            )

        production_section = format_production_code(
            sample.get("code_under_test_json")
        )

        if production_section:
            sections.append(production_section)

    return "\n\n".join(sections)


def build_prompt(
    sample: dict,
    strategy: str = "zero_shot",
    include_context: bool = True
) -> str:

    system_prompt = load_prompt(
        "system_prompt.txt"
    )

    task_instruction = load_prompt(
        "task_instruction.txt"
    )

    category_definitions = load_prompt(
        "category_definitions.txt"
    )

    strategy_prompt = load_prompt(
        f"strategies/{strategy}.txt"
    )

    output_format = load_prompt(
        "output_format.txt"
    )

    input_section = build_input_section(
        sample,
        include_context
    )

    prompt_parts = [
        system_prompt,
        task_instruction,
        category_definitions,
        strategy_prompt,
    ]

    # Add worked examples only for Few-shot CoT
    if strategy == "few_shot_cot":

        if include_context:
            few_shot_examples = load_prompt(
                "examples/few_shot_context.txt"
            )
        else:
            few_shot_examples = load_prompt(
                "examples/few_shot_code_only.txt"
            )

        prompt_parts.append(few_shot_examples)

    # Add target input
    prompt_parts.append(input_section)

    # Add output specification
    prompt_parts.append(output_format)

    return "\n\n".join(prompt_parts)