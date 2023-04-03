"""
This is a modified setup.py file from the edgedb project.
The original file can be found at:
    https://github.com/edgedb/edgedb/blob/master/setup.py

The original file is licensed under the Apache License, Version 2.0.

The modifications are licensed under the MIT License.

Copyright 2023 - present, Soof Golan.

Original License below

#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2008-present MagicStack Inc. and the EdgeDB authors.
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
#
"""


import os
import os.path
import pathlib
import platform
import shutil
import subprocess

import setuptools
from setuptools.command import build as setuptools_build

ROOT_PATH = pathlib.Path(__file__).parent.resolve()


def _get_env_with_openssl_flags():
    env = dict(os.environ)
    cflags = env.get("TINYPG_BUILD_OPENSSL_CFLAGS")
    ldflags = env.get("TINYPG_BUILD_OPENSSL_LDFLAGS")

    if not (cflags or ldflags) and platform.system() == "Darwin":
        try:
            openssl_prefix = pathlib.Path(
                subprocess.check_output(
                    ["brew", "--prefix", "openssl"], text=True
                ).strip()
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            openssl_prefix = None
        else:
            pc_path = str(openssl_prefix / "lib" / "pkgconfig")
            if "PKG_CONFIG_PATH" in env:
                env["PKG_CONFIG_PATH"] += f":{pc_path}"
            else:
                env["PKG_CONFIG_PATH"] = pc_path
        try:
            cflags = subprocess.check_output(
                ["pkg-config", "--cflags", "openssl"], text=True, env=env
            ).strip()
            ldflags = subprocess.check_output(
                ["pkg-config", "--libs", "openssl"], text=True, env=env
            ).strip()
        except FileNotFoundError:
            # pkg-config is not installed
            if openssl_prefix:
                cflags = f'-I{openssl_prefix / "include"!s}'
                ldflags = f'-L{openssl_prefix / "lib"!s}'
            else:
                return env
        except subprocess.CalledProcessError:
            # Cannot find flags with pkg-config
            return env

    if cflags:
        if "CPPFLAGS" in env:
            env["CPPFLAGS"] += f" {cflags}"
        elif "CFLAGS" in env:
            env["CFLAGS"] += f" {cflags}"
        else:
            env["CPPFLAGS"] = cflags
    if ldflags:
        if "LDFLAGS" in env:
            env["LDFLAGS"] += f" {ldflags}"
        else:
            env["LDFLAGS"] = ldflags
    return env


def _compile_postgres(
    build_base,
    *,
    force_build=False,
    fresh_build=True,
    run_configure=True,
    build_contrib=True,
    produce_compile_commands_json=False,
):
    # TODO: use a better way to detect changes in the source
    # source_stamp = _get_pg_source_stamp()
    source_stamp = None
    # logging.error(source_stamp)

    postgres_build = (build_base / "postgres").resolve()
    postgres_src = ROOT_PATH / "vendor" / "postgres"
    postgres_build_stamp = postgres_build / "stamp"

    if postgres_build_stamp.exists():
        with open(postgres_build_stamp, "r") as f:
            build_stamp = f.read()
    else:
        build_stamp = None

    is_outdated = False  # source_stamp != build_stamp

    if is_outdated or force_build:
        system = platform.system()
        if system == "Darwin":
            uuidlib = "e2fs"
        elif system == "Linux":
            uuidlib = "e2fs"
        else:
            raise NotImplementedError("unsupported system: {}".format(system))

        if fresh_build and postgres_build.exists():
            shutil.rmtree(postgres_build)
        build_dir = postgres_build / "build"
        if not build_dir.exists():
            build_dir.mkdir(parents=True)
        if not run_configure:
            run_configure = not (build_dir / "Makefile").exists()

        if run_configure or fresh_build or is_outdated:
            env = _get_env_with_openssl_flags()
            subprocess.run(
                [
                    str(postgres_src / "configure"),
                    "--prefix=" + str(postgres_build / "install"),
                    "--with-openssl",
                    "--with-uuid=" + uuidlib,
                ],
                check=True,
                cwd=str(build_dir),
                env=env,
            )

        if produce_compile_commands_json:
            make = ["bear", "--", "make"]
        else:
            make = ["make"]

        subprocess.run(
            make + ["MAKELEVEL=0", "-j", str(max(os.cpu_count() - 1, 1))],
            cwd=str(build_dir),
            check=True,
        )

        if build_contrib or fresh_build or is_outdated:
            subprocess.run(
                make
                + [
                    "-C",
                    "contrib",
                    "MAKELEVEL=0",
                    "-j",
                    str(max(os.cpu_count() - 1, 1)),
                ],
                cwd=str(build_dir),
                check=True,
            )

        subprocess.run(
            ["make", "MAKELEVEL=0", "install"], cwd=str(build_dir), check=True
        )

        if build_contrib or fresh_build or is_outdated:
            subprocess.run(
                ["make", "-C", "contrib", "MAKELEVEL=0", "install"],
                cwd=str(build_dir),
                check=True,
            )

        # with open(postgres_build_stamp, "w") as f:
        #     f.write(source_stamp)

        if produce_compile_commands_json:
            shutil.copy(
                build_dir / "compile_commands.json",
                postgres_src / "compile_commands.json",
            )


def _get_pg_source_stamp():
    proc = subprocess.run(
        ["git", "submodule", "status", "vendor/postgres"],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        check=True,
        cwd=ROOT_PATH,
    )
    status = proc.stdout
    if status[0] == "-":
        print(
            "postgres submodule not initialized, "
            "run `git submodule init; git submodule update`"
        )
        exit(1)

    output = subprocess.check_output(
        ["git", "submodule", "status", "vendor/postgres"],
        universal_newlines=True,
        cwd=ROOT_PATH,
    )
    revision, _, _ = output[1:].partition(" ")
    # I don't know why we needed the first empty char, but we don't want to
    # force everyone to rebuild postgres either
    source_stamp = output[0] + revision
    return source_stamp


class build(setuptools_build.build):
    user_options = setuptools_build.build.user_options

    sub_commands = [
        *setuptools_build.build.sub_commands,
        ("build_postgres", lambda self: True),
    ]


class build_postgres(setuptools.Command):
    description = "build postgres"

    user_options = [
        ("configure", None, "run ./configure"),
        ("build-contrib", None, "build contrib"),
        ("fresh-build", None, "rebuild from scratch"),
        ("compile-commands", None, "produce compile-commands.json using bear"),
    ]

    editable_mode: bool

    def initialize_options(self):
        self.editable_mode = False
        self.configure = False
        self.build_contrib = False
        self.fresh_build = False
        self.compile_commands = False

    def finalize_options(self):
        pass

    def run(self, *args, **kwargs):
        if os.environ.get("TINYPG_BUILD_PACKAGE"):
            return
        build = self.get_finalized_command("build")
        _compile_postgres(
            pathlib.Path(build.build_base).resolve(),
            force_build=True,
            fresh_build=self.fresh_build,
            run_configure=self.configure,
            build_contrib=self.build_contrib,
            produce_compile_commands_json=self.compile_commands,
        )


setuptools.setup(
    name="tiny-postgres",
    version="0.1.0",
    cmdclass={
        "build": build,
        "build_postgres": build_postgres,
    },
    py_modules=[],
)
