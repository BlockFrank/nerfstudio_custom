# Copyright 2022 the Regents of the University of California, Nerfstudio Team and contributors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Module that keeps all registered plugins and allows for plugin discovery.
"""

from __future__ import annotations

from typing import Dict, Tuple

from rich.console import Console

from nerfstudio.plugins.types import MethodSpecification

CONSOLE = Console(width=120)

try:
    from importlib.metadata import entry_points
except ImportError:
    from importlib_metadata import entry_points


def discover_methods() -> Tuple[Dict[str, MethodSpecification], Dict[str, str]]:
    """
    Discover external nerfstudio methods via entry points.

    IMPORTANT:
    This loader is intentionally resilient:
    - broken external methods are skipped
    - import/load errors do not crash nerfstudio CLI
    """
    methods: Dict[str, MethodSpecification] = {}
    descriptions: Dict[str, str] = {}

    discovered_entry_points = entry_points(group="nerfstudio.method_configs")

    # Compat for different importlib.metadata return types
    try:
        names = discovered_entry_points.names
        get_ep = lambda name: discovered_entry_points[name]
    except AttributeError:
        eps_by_name = {ep.name: ep for ep in discovered_entry_points}
        names = eps_by_name.keys()
        get_ep = lambda name: eps_by_name[name]

    for name in names:
        ep = get_ep(name)

        try:
            spec = ep.load()
        except Exception as exc:
            CONSOLE.print(
                f"[bold yellow]Warning:[/bold yellow] Skipping external method "
                f"[cyan]{name}[/cyan] because it failed to import/load.\n"
                f"  Entry point: {ep.value}\n"
                f"  Error: {type(exc).__name__}: {exc}"
            )
            continue

        if not isinstance(spec, MethodSpecification):
            CONSOLE.print(
                f"[bold yellow]Warning:[/bold yellow] Skipping external method "
                f"[cyan]{name}[/cyan] because loaded object is not a MethodSpecification.\n"
                f"  Loaded object type: {type(spec).__name__}"
            )
            continue

        methods[name] = spec
        descriptions[name] = spec.description

    return methods, descriptions