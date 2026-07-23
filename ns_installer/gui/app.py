from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterator

from ns_installer.core.methods import resolved_method_catalog
import gradio as gr

from ns_installer.cli.commands.methods import discover_all_trainable_methods
from ns_installer import ROOT
from ns_installer.core.methods import discover_method_entrypoints, known_method_names

def get_method_choices() -> list[tuple[str, str]]:
    from ns_installer.core.methods import gui_method_choices
    return gui_method_choices()


def default_output_dir() -> str:
    return str((ROOT / "outputs").resolve())


def build_train_command(
    method: str,
    dataset_path: str,
    output_dir: str,
    extra_args: str = "",
) -> str:
    dataset_path = (dataset_path or "").strip()
    output_dir = (output_dir or "").strip()
    extra_args = (extra_args or "").strip()

    if not method:
        return ""

    parts = ["ns-train", method]

    if dataset_path:
        parts.extend(["--data", f'"{dataset_path}"'])

    if output_dir:
        parts.extend(["--output-dir", f'"{output_dir}"'])

    if extra_args:
        parts.append(extra_args)

    return " ".join(parts)


def refresh_methods(current_value: str | None) -> gr.Dropdown:
    choices = get_method_choices()
    valid_values = [value for _, value in choices]

    if current_value in valid_values:
        value = current_value
    else:
        value = valid_values[0] if valid_values else None

    return gr.Dropdown(choices=choices, value=value)


def update_command_preview(method: str, dataset_path: str, output_dir: str, extra_args: str) -> str:
    return build_train_command(method, dataset_path, output_dir, extra_args)


def stream_training_logs(
    method: str,
    dataset_path: str,
    output_dir: str,
    extra_args: str,
) -> Iterator[tuple[str, str]]:
    cmd_preview = build_train_command(method, dataset_path, output_dir, extra_args)

    if not method:
        yield "", "[ERR] No method selected."
        return

    if not dataset_path.strip():
        yield cmd_preview, "[ERR] Dataset path is required."
        return

    if not output_dir.strip():
        yield cmd_preview, "[ERR] Output directory is required."
        return

    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    cmd = ["ns-train", method, "--data", dataset_path, "--output-dir", str(output_path)]
    if extra_args.strip():
        # Keep shell-like user flexibility, but split conservatively.
        import shlex
        cmd.extend(shlex.split(extra_args))

    env = os.environ.copy()
    logs: list[str] = [f"[CMD] {cmd_preview}\n\n"]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            env=env,
        )
    except Exception as e:
        logs.append(f"[ERR] Failed to launch training: {type(e).__name__}: {e}\n")
        yield cmd_preview, "".join(logs)
        return

    assert process.stdout is not None
    for line in process.stdout:
        logs.append(line)
        yield cmd_preview, "".join(logs)

    rc = process.wait()
    logs.append(f"\n[EXIT] Process finished with code {rc}\n")
    yield cmd_preview, "".join(logs)
    
def resolved_method_catalog_debug_text() -> str:
    rows = resolved_method_catalog()
    lines = []
    for row in rows:
        lines.append(
            f"{row['display_name']} | train={row['train_name']} | "
            f"installer={row.get('installer_name')} | "
            f"entrypoint={row.get('entrypoint_name')} | "
            f"source={row['source']}"
        )
    return "\n".join(lines)
def get_method_debug_summary() -> str:
    from ns_installer.cli.commands.methods import discover_all_trainable_methods
    from ns_installer.core.methods import discover_method_entrypoints, known_method_names

    lines: list[str] = []

    try:
        info = discover_all_trainable_methods()
        lines.append(f"[methods] available source: {info.get('source', 'unknown')}")
        lines.append(f"[methods] available count: {len(info.get('methods', []))}")
        if "error" in info:
            lines.append(f"[methods] available error: {info['error']}")
    except Exception as e:
        lines.append(f"[methods] available exception: {type(e).__name__}: {e}")

    try:
        discovered = discover_method_entrypoints()
        lines.append(f"[methods] entrypoint count: {len(discovered)}")
    except Exception as e:
        lines.append(f"[methods] entrypoint exception: {type(e).__name__}: {e}")

    try:
        known = known_method_names()
        lines.append(f"[methods] known fallback count: {len(known)}")
    except Exception as e:
        lines.append(f"[methods] known fallback exception: {type(e).__name__}: {e}")

    return "\n".join(lines)

def build_app() -> gr.Blocks:
    methods = get_method_choices()
    initial_method = methods[0][1] if methods else None

    with gr.Blocks(title="ns-install Training GUI") as app:
        gr.Markdown("# ns-install Training GUI")
        gr.Markdown("Launch Nerfstudio training with method discovery and live logs.")

        with gr.Row():
            method = gr.Dropdown(
                label="Method",
                choices=methods,
                value=initial_method,
                allow_custom_value=False,
            )
            refresh_btn = gr.Button("Refresh Methods")

        dataset_path = gr.Textbox(
            label="Dataset Path",
            placeholder=r"F:\NerfDatasets(Test+Custom)\data\scene_name",
        )

        output_dir = gr.Textbox(
            label="Output Directory",
            value=default_output_dir(),
            placeholder=r"E:\nerfstudio\outputs",
        )

        extra_args = gr.Textbox(
            label="Extra Args",
            placeholder='--vis viewer+tensorboard',
        )

        command_preview = gr.Textbox(
            label="Command Preview",
            interactive=False,
        )

        run_btn = gr.Button("Run Training", variant="primary")

        logs = gr.Textbox(
            label="Log Panel",
            value=get_method_debug_summary(),
            lines=24,
            max_lines=30,
            interactive=False,
        )

        refresh_btn.click(
            fn=refresh_methods,
            inputs=method,
            outputs=method,
        )

        for component in (method, dataset_path, output_dir, extra_args):
            component.change(
                fn=update_command_preview,
                inputs=[method, dataset_path, output_dir, extra_args],
                outputs=command_preview,
            )

        run_btn.click(
            fn=stream_training_logs,
            inputs=[method, dataset_path, output_dir, extra_args],
            outputs=[command_preview, logs],
        )

    return app


def launch_gui() -> None:
    app = build_app()
    app.launch()


if __name__ == "__main__":
    launch_gui()