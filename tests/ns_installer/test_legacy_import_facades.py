from importlib import import_module

DIRECT_EXPECTED = {'ns_installer.bootstrap': ['apply_cuda_env_policy', 'build_bootstrap_context', 'build_bootstrap_env', 'choose_msvc_toolset', 'detect_cuda_root', 'detect_git_dirs', 'find_header_in_include', 'get_runtime_path_entries', 'list_msvc_toolsets', 'normalize_selected_toolset', 'normalize_windows_path_list', 'parse_set_output_to_env', 'print_run', 'print_run_bootstrapped', 'run', 'run_bootstrapped', 'sanitize_windows_path', 'short_toolset_version', 'validate_msvc_from_shell', 'vswhere_path', 'which', 'write_bootstrap_env_snapshot', 'write_msvc_log'], 'ns_installer.build': ['BUILD_TOOL_PKGS', 'PIP_VERBOSE_ARGS', 'build_tetra_nerf_windows', 'build_zipnerf_cuda_windows', 'choose_conda_restore_cmd', 'current_tcnn_arch', 'detect_tcnn_runtime', 'ensure_build_tooling_for_cpp', 'ensure_numpy_stable', 'filter_already_installed_exact_specs', 'get_installed_version', 'git_requirement_matches', 'install_av', 'install_deferred', 'install_editable_project', 'install_packaging_base', 'install_pyg_wheels', 'install_remaining_from_full_lock', 'install_requirements_file', 'install_tcnn', 'install_torch_preinstall', 'installed_direct_url_map', 'installed_pip_map', 'maybe_build_method_native', 'normalized_current_pip_lines', 'print_strict_alignment_status', 'repin_after_method_install', 'restore_core_overrides', 'restore_protected_from_lock', 'spec_is_exact_pin', 'tcnn_runtime_ok', 'torch_cuda_arch_list_value', 'torch_pyg_tag'], 'ns_installer.doctor': ['diagnose', 'main'], 'ns_installer.patches': ['PATCHABLE_REPOS', 'SKIP_FILENAMES', 'SKIP_SUFFIXES', 'apply_extra_patches', 'apply_repo_patches', 'list_available_patch_roots']}
CORE_EXPECTED = ['check_locks', 'diff_summary', 'install_all', 'install_core', 'normalized_current_pip_lines', 'repin']

def test_direct_legacy_facades_export_historical_surface():
    for legacy_name, expected_names in DIRECT_EXPECTED.items():
        legacy = import_module(legacy_name)
        canonical = import_module('ns_installer.core.' + legacy_name.rsplit('.', 1)[-1])
        for name in expected_names:
            assert hasattr(legacy, name), (legacy_name, name)
            assert getattr(legacy, name) is getattr(canonical, name)

def test_core_package_preserves_safe_historical_surface():
    core = import_module('ns_installer.core')
    for name in CORE_EXPECTED:
        assert hasattr(core, name), name
