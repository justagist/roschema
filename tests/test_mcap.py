"""Tests for McapTypeFS and bag-check.

The ros2msg splitter and ros2idl converter are pure functions and are tested
directly; the end-to-end path builds a real MCAP with the mcap writer (skipped
when the optional 'bag' extra is not installed).
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from _helpers import write_package
from roschema.cli import app
from roschema.mcap_fs import _convert_ros2idl, _split_ros2msg

runner = CliRunner()

# A concatenated ros2msg definition: main type plus one dependent type.
POSE_CONCAT = (
    "float32 theta\n"
    "geometry_msgs/Point position\n"
    "================================================================================\n"
    "MSG: geometry_msgs/Point\n"
    "float64 x\n"
    "float64 y\n"
)
POSE_V1 = "float32 theta\ngeometry_msgs/Point position\n"  # matches the bag
POSE_V2 = "float64 theta\ngeometry_msgs/Point position\n"  # theta widened
POINT = "float64 x\nfloat64 y\n"


def test_split_ros2msg_attributes_blocks():
    blocks = _split_ros2msg("demo_msgs/msg/Pose", POSE_CONCAT)
    assert set(blocks) == {"demo_msgs/msg/Pose", "geometry_msgs/msg/Point"}
    assert blocks["demo_msgs/msg/Pose"] == "float32 theta\ngeometry_msgs/Point position"
    assert blocks["geometry_msgs/msg/Point"] == "float64 x\nfloat64 y"


def test_split_ros2msg_service_event_and_empty_message():
    """Service events carry only an SRV block; a field-less message stays a message."""
    event = "=" * 80 + "\nSRV: demo_srvs/srv/Add\nint64 a\n---\nint64 sum\n"
    assert _split_ros2msg("demo_srvs/srv/Add_Event", event) == {
        "demo_srvs/srv/Add": "int64 a\n---\nint64 sum"
    }
    assert _split_ros2msg("std_msgs/msg/Empty", "") == {"std_msgs/msg/Empty": ""}
    holder = "std_msgs/Empty e\n" + "=" * 80 + "\nMSG: std_msgs/Empty\n"
    assert _split_ros2msg("demo/msg/Holder", holder) == {
        "demo/msg/Holder": "std_msgs/Empty e",
        "std_msgs/msg/Empty": "",
    }


def test_convert_ros2idl_subset():
    idl = """
    module demo_msgs {
      module msg {
        struct Foo {
          const int32 MODE = 5;
          int32 a;
          sequence<double> b;
          sequence<int32, 8> bounded;
          string<10> name;
          double matrix[3];
          geometry_msgs::msg::Point point;
        };
      };
    };
    """
    blocks = _convert_ros2idl(idl)
    assert "demo_msgs/msg/Foo" in blocks
    body = blocks["demo_msgs/msg/Foo"]
    assert "int32 MODE=5" in body
    assert "int32 a" in body
    assert "float64[] b" in body
    assert "int32[<=8] bounded" in body
    assert "string<=10 name" in body
    assert "float64[3] matrix" in body
    assert "geometry_msgs/Point point" in body


@pytest.mark.parametrize("value", ["enum Choice", "const int32 MODE = 1", "struct U {", "}"])
def test_convert_ros2idl_accepts_keywords_in_string_constants(value):
    """Declaration-like string contents must not affect IDL validation or structure."""
    idl = (
        'module demo { module msg { struct T { const string NOTE = "'
        + value
        + '"; int32 x; }; }; };'
    )
    assert _convert_ros2idl(idl) == {"demo/msg/T": f'string NOTE="{value}"\nint32 x'}


# --- end-to-end with a real MCAP ---

pytest.importorskip("mcap")


def _write_bag(
    path, schemas: dict[str, str] | list[tuple[str, str, str]], *, summary: bool = True
) -> None:
    from mcap.writer import Writer

    with open(path, "wb") as handle:
        writer = Writer(handle, repeat_schemas=summary)
        writer.start()
        entries = (
            [(name, "ros2msg", text) for name, text in schemas.items()]
            if isinstance(schemas, dict)
            else schemas
        )
        for name, encoding, text in entries:
            schema_id = writer.register_schema(name=name, encoding=encoding, data=text.encode())
            channel_id = writer.register_channel(
                topic="/" + name.replace("/", "_"),
                message_encoding="cdr",
                schema_id=schema_id,
            )
            writer.add_message(channel_id=channel_id, log_time=0, data=b"", publish_time=0)
        writer.finish()


def test_mcap_type_fs_virtual_tree(tmp_path):
    from roschema.mcap_fs import McapTypeFS

    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"demo_msgs/msg/Pose": POSE_CONCAT})
    fs = McapTypeFS(str(bag))
    msgs = fs.glob("**/*.msg")
    assert "demo_msgs/msg/Pose.msg" in msgs
    assert "geometry_msgs/msg/Point.msg" in msgs
    assert fs.exists("demo_msgs/package.xml")
    assert fs.read_text("geometry_msgs/msg/Point.msg").strip() == "float64 x\nfloat64 y"


def test_bag_check_reports_findings(tmp_path):
    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"demo_msgs/msg/Pose": POSE_CONCAT})
    ws = tmp_path / "ws"
    # current tree: Pose.theta changed float32 -> float64; deps present so no noise
    write_package(ws, "demo_msgs", msgs={"Pose": POSE_V2})
    write_package(ws, "geometry_msgs", msgs={"Point": POINT})

    result = runner.invoke(app, ["bag-check", str(bag), str(ws)])
    assert result.exit_code == 1
    assert "RS003" in result.stdout
    assert "theta" in result.stdout


def test_check_against_mcap_baseline(tmp_path):
    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"demo_msgs/msg/Pose": POSE_CONCAT})
    ws = tmp_path / "ws"
    write_package(ws, "demo_msgs", msgs={"Pose": POSE_V2})
    write_package(ws, "geometry_msgs", msgs={"Point": POINT})

    result = runner.invoke(app, ["check", str(ws), "--against", str(bag)])
    assert result.exit_code == 1
    assert "RS003" in result.stdout


def test_bag_check_rejects_non_mcap(tmp_path):
    result = runner.invoke(app, ["bag-check", "notabag.txt", str(tmp_path)])
    assert result.exit_code == 2


def test_bag_check_defaults_to_environment(tmp_path, monkeypatch):
    # No targets: the bag is compared against the current environment (ament).
    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"demo_msgs/msg/Pose": POSE_CONCAT})
    prefix = tmp_path / "install"
    # installed demo_msgs changed Pose.theta float32 -> float64; geometry_msgs matches
    write_package(prefix / "share", "demo_msgs", msgs={"Pose": POSE_V2})
    write_package(prefix / "share", "geometry_msgs", msgs={"Point": POINT})
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(prefix))

    result = runner.invoke(app, ["bag-check", str(bag)])
    assert result.exit_code == 1
    assert "RS003" in result.stdout and "theta" in result.stdout


def test_bag_check_type_missing_from_environment_is_removed(tmp_path, monkeypatch):
    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"demo_msgs/msg/Pose": POSE_CONCAT})
    prefix = tmp_path / "install"
    # demo_msgs matches the bag, but geometry_msgs is not installed at all
    write_package(prefix / "share", "demo_msgs", msgs={"Pose": POSE_V1})
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(prefix))

    result = runner.invoke(app, ["bag-check", str(bag)])
    assert result.exit_code == 1
    assert "RS040" in result.stdout
    assert "geometry_msgs/msg/Point" in result.stdout


def test_bag_check_target_overrides_environment(tmp_path, monkeypatch):
    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"demo_msgs/msg/Pose": POSE_CONCAT})
    prefix = tmp_path / "install"
    # environment alone matches the bag (would exit 0)
    write_package(prefix / "share", "demo_msgs", msgs={"Pose": POSE_V1})
    write_package(prefix / "share", "geometry_msgs", msgs={"Point": POINT})
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(prefix))
    # a local source tree overrides demo_msgs with a breaking change
    ws = tmp_path / "ws"
    write_package(ws, "demo_msgs", msgs={"Pose": POSE_V2})

    result = runner.invoke(app, ["bag-check", str(bag), str(ws)])
    assert result.exit_code == 1
    assert "RS003" in result.stdout and "theta" in result.stdout


def test_bag_check_multiple_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("AMENT_PREFIX_PATH", "")  # no environment; targets drive it
    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"pkg_a/msg/A": "float32 a\n", "pkg_b/msg/B": "int32 b\n"})
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    write_package(dir_a, "pkg_a", msgs={"A": "float64 a\n"})  # widened
    write_package(dir_b, "pkg_b", msgs={"B": "int64 b\n"})  # widened

    result = runner.invoke(app, ["bag-check", str(bag), str(dir_a), str(dir_b)])
    assert result.exit_code == 1
    ids = result.stdout
    assert "pkg_a/msg/A" in ids and "pkg_b/msg/B" in ids


def test_glob_rejects_synthetic_mcap_paths(tmp_path, monkeypatch):
    write_package(tmp_path / "src", "demo_msgs", msgs={"Pose": POSE_V1})
    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"demo_msgs/msg/Pose": POSE_CONCAT})
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["check", "src/**", "--against", str(bag)])
    assert result.exit_code == 2
    assert "use a workspace target" in " ".join(result.output.split())


@pytest.mark.parametrize(
    "summary,reverse,command",
    [
        (True, False, "bag-check"),
        (True, True, "bag-check"),
        (False, False, "bag-check"),
        (True, False, "check"),
    ],
)
def test_mcap_rejects_conflicting_schemas_in_either_order(tmp_path, summary, reverse, command):
    bag = tmp_path / "conflict.mcap"
    schemas = [
        ("demo/msg/T", "ros2msg", "int32 x\n"),
        ("demo/msg/T", "ros2msg", "float64 x\n"),
    ]
    _write_bag(bag, schemas[::-1] if reverse else schemas, summary=summary)
    write_package(tmp_path / "ws", "demo", msgs={"T": "int32 x\n"})
    args = (
        ["bag-check", str(bag), str(tmp_path / "ws")]
        if command == "bag-check"
        else ["check", str(tmp_path / "ws"), "--against", str(bag)]
    )
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "conflicting MCAP definitions" in result.output


def test_mcap_accepts_equivalent_duplicate_definitions(tmp_path):
    bag = tmp_path / "equivalent.mcap"
    _write_bag(
        bag,
        [
            ("demo/msg/T", "ros2msg", "int32 x\n"),
            ("demo/T", "ros2msg", "int32   x # another comment\n"),
        ],
    )
    write_package(tmp_path / "ws", "demo", msgs={"T": "int32 x\n"})
    result = runner.invoke(app, ["bag-check", str(bag), str(tmp_path / "ws")])
    assert result.exit_code == 0


@pytest.mark.parametrize("same_schema", [True, False])
def test_mcap_rejects_conflicting_embedded_definitions(tmp_path, same_schema):
    bag = tmp_path / "dependencies.mcap"
    first = "int32 x\n===\nMSG: demo/Dep\nint32 value\n"
    second = "int32 x\n===\nMSG: demo/Dep\nfloat64 value\n"
    schemas = (
        [("demo/msg/T", "ros2msg", first + "===\nMSG: demo/Dep\nfloat64 value\n")]
        if same_schema
        else [
            ("demo/msg/T", "ros2msg", first),
            ("demo/msg/U", "ros2msg", second),
        ]
    )
    _write_bag(bag, schemas)
    result = runner.invoke(app, ["bag-check", str(bag)])
    assert result.exit_code == 2
    assert "conflicting MCAP definitions" in result.output


@pytest.mark.parametrize("with_supported", [True, False])
def test_mcap_rejects_unsupported_encodings(tmp_path, with_supported):
    bag = tmp_path / "unsupported.mcap"
    schemas = [("demo/msg/T", "jsonschema", "{}")]
    if with_supported:
        schemas.append(("demo/msg/U", "ros2msg", "int32 value\n"))
    _write_bag(bag, schemas)
    result = runner.invoke(app, ["bag-check", str(bag)])
    assert result.exit_code == 2
    assert "unsupported MCAP schema encoding" in result.output
    assert "jsonschema" in result.output


@pytest.mark.parametrize(
    "idl",
    [
        "module demo { module msg { enum Choice { A, B }; struct T { Choice x; }; }; };",
        "module demo { module msg { struct T { int32 x; }; struct U { unknown x; }; }; };",
        "module demo { module msg { @unsupported struct T { int32 x; }; }; };",
        "module demo { module msg { const long MODE = 1; struct T { long x; }; }; };",
        "module demo { module msg { struct T { long x; }; module T_Constants { "
        "const long MODE = 1; }; }; };",
        "module demo { module msg { struct Base { long x; }; struct T : Base { long y; }; }; };",
        "module demo { module msg { struct T { wchar c; }; }; };",  # no msg equivalent
    ],
)
def test_mcap_rejects_partial_idl_conversion(tmp_path, idl):
    bag = tmp_path / "unsupported-idl.mcap"
    _write_bag(bag, [("demo/msg/T", "ros2idl", idl)])
    result = runner.invoke(app, ["bag-check", str(bag)])
    assert result.exit_code == 2
    assert "unsupported ros2idl" in result.output


def test_bag_check_skips_schemas_without_definitions(tmp_path, monkeypatch):
    prefix = tmp_path / "install"
    write_package(prefix / "share", "demo_msgs", msgs={"Pose": POSE_V2})
    write_package(prefix / "share", "geometry_msgs", msgs={"Point": POINT})
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(prefix))
    bag = tmp_path / "missing.mcap"
    _write_bag(
        bag,
        [("demo_msgs/msg/Pose", "ros2msg", POSE_CONCAT), ("demo_msgs/action/Go_Feedback", "", "")],
    )
    result = runner.invoke(app, ["bag-check", str(bag)])
    assert result.exit_code == 1
    assert "RS003" in result.stdout
    assert "demo_msgs/action/Go_Feedback" in result.output


def test_bag_check_compares_service_event_definitions(tmp_path, monkeypatch):
    prefix = tmp_path / "install"
    write_package(prefix / "share", "demo_srvs", srvs={"Add": "int64 a\n---\nint32 sum\n"})
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(prefix))
    bag = tmp_path / "events.mcap"
    event = "=" * 80 + "\nSRV: demo_srvs/srv/Add\nint64 a\n---\nint64 sum\n"
    _write_bag(bag, {"demo_srvs/srv/Add_Event": event})
    result = runner.invoke(app, ["bag-check", str(bag), "--format", "json"])
    assert result.exit_code == 1
    finding = json.loads(result.stdout)["findings"][0]
    assert (finding["rule"], finding["interface"], finding["section"]) == (
        "RS003",
        "demo_srvs/srv/Add",
        "response",
    )


def test_bag_check_accepts_field_less_messages(tmp_path, monkeypatch):
    prefix = tmp_path / "install"
    write_package(prefix / "share", "std_msgs", msgs={"Empty": ""})
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(prefix))
    bag = tmp_path / "empty-message.mcap"
    _write_bag(bag, {"std_msgs/msg/Empty": ""})
    result = runner.invoke(app, ["bag-check", str(bag)])
    assert result.exit_code == 0, result.output


def test_bag_check_defaults_to_wire_level(tmp_path, monkeypatch):
    """Constant changes do not stop current code decoding a recording."""
    prefix = tmp_path / "install"
    write_package(prefix / "share", "demo_msgs", msgs={"Mode": "int32 x\n"})
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(prefix))
    monkeypatch.chdir(tmp_path)
    bag = tmp_path / "constants.mcap"
    _write_bag(bag, {"demo_msgs/msg/Mode": "int32 IDLE=0\nint32 x\n"})

    default = runner.invoke(app, ["bag-check", str(bag)])
    assert default.exit_code == 0, default.output
    assert "RS020" not in default.stdout
    source = runner.invoke(app, ["bag-check", str(bag), "--level", "source"])
    assert source.exit_code == 1
    assert "RS020" in source.stdout
    (tmp_path / "roschema.toml").write_text('[check]\nlevel = "source"\n')
    configured = runner.invoke(app, ["bag-check", str(bag)])
    assert configured.exit_code == 1


def test_bag_check_applies_target_package_config(tmp_path, monkeypatch):
    write_package(tmp_path / "src", "demo", msgs={"T": "float64 x\n"})
    (tmp_path / "src" / "demo" / "roschema.toml").write_text('[check.rules]\nRS003 = "off"\n')
    monkeypatch.chdir(tmp_path)
    bag = tmp_path / "target-config.mcap"
    _write_bag(bag, {"demo/msg/T": "int32 x\n"})
    result = runner.invoke(app, ["bag-check", str(bag), "src/demo", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["findings"] == []


def test_bag_check_last_target_drops_earlier_target_config(tmp_path, monkeypatch):
    """A replaced package's configuration must not apply to its replacement."""
    first = write_package(tmp_path / "first", "demo", msgs={"T": "int32 x\n"})
    (first / "roschema.toml").write_text('[check.rules]\nRS003 = "off"\n')
    write_package(tmp_path / "second", "demo", msgs={"T": "float64 x\n"})
    monkeypatch.chdir(tmp_path)
    bag = tmp_path / "replaced.mcap"
    _write_bag(bag, {"demo/msg/T": "int32 x\n"})
    result = runner.invoke(app, ["bag-check", str(bag), "first/demo", "second/demo"])
    assert result.exit_code == 1
    assert "RS003" in result.stdout


def test_bag_check_with_everything_excluded_is_an_error(tmp_path):
    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"demo_msgs/msg/Pose": POSE_CONCAT})
    ws = tmp_path / "ws"
    write_package(ws, "demo_msgs", msgs={"Pose": POSE_V2})
    write_package(ws, "geometry_msgs", msgs={"Point": POINT})

    result = runner.invoke(app, ["bag-check", str(bag), str(ws), "--exclude", "*"])
    assert result.exit_code == 2
    assert "the bag has no interfaces" in result.output
    assert "--exclude" in result.output
    assert "--allow-empty" not in result.output


def test_bag_check_github_attaches_unlocated_findings_to_interface_file(tmp_path):
    bag = tmp_path / "rec.mcap"
    _write_bag(bag, {"demo_msgs/msg/Pose": POSE_CONCAT})
    ws = tmp_path / "ws"
    write_package(ws, "demo_msgs", msgs={"Pose": "geometry_msgs/Point position\n"})
    write_package(ws, "geometry_msgs", msgs={"Point": POINT})

    result = runner.invoke(app, ["bag-check", str(bag), str(ws), "--format", "github"])
    assert result.exit_code == 1
    removed = [line for line in result.stdout.splitlines() if "title=RS001" in line]
    assert removed
    assert all(line.startswith("::error file=demo_msgs/msg/Pose.msg,") for line in removed)


def test_mcap_without_schemas_is_a_tool_error(tmp_path):
    bag = tmp_path / "empty.mcap"
    _write_bag(bag, {})
    result = runner.invoke(app, ["bag-check", str(bag)])
    assert result.exit_code == 2
    assert "no usable ROS schemas" in result.output


@pytest.mark.parametrize("remaining", [{"Other": "int32 y\n"}, {}])
def test_bag_source_package_replaces_all_installed_interfaces(tmp_path, monkeypatch, remaining):
    bag = tmp_path / "deleted.mcap"
    _write_bag(bag, {"demo/msg/T": "int32 x\n", "system/msg/U": "int32 x\n"})
    prefix = tmp_path / "install"
    write_package(prefix / "share", "demo", msgs={"T": "int32 x\n"})
    write_package(prefix / "share", "system", msgs={"U": "int32 x\n"})
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(prefix))
    source = tmp_path / "source"
    write_package(source, "demo", msgs=remaining)

    result = runner.invoke(app, ["bag-check", str(bag), str(source), "--format", "json"])
    assert result.exit_code == 1
    findings = json.loads(result.stdout)["findings"]
    assert [(f["rule"], f["interface"]) for f in findings] == [("RS040", "demo/msg/T")]


def test_last_source_target_replaces_previous_package(tmp_path):
    bag = tmp_path / "overlap.mcap"
    _write_bag(bag, {"demo/msg/T": "int32 x\n"})
    first, second = tmp_path / "first", tmp_path / "second"
    write_package(first, "demo", msgs={"T": "int32 x\n"})
    write_package(second, "demo", msgs={"Other": "int32 y\n"})
    result = runner.invoke(app, ["bag-check", str(bag), str(first), str(second)])
    assert result.exit_code == 1
    assert "RS040" in result.stdout


@pytest.mark.parametrize("package_format", ["roschema.toml", "pyproject.toml"])
def test_bag_check_uses_current_package_config(tmp_path, monkeypatch, package_format):
    """Bag checks retain inherited rules and current-package severity overrides."""
    bag = tmp_path / "config.mcap"
    _write_bag(bag, {"demo/msg/T": "int32 x\n", "other/msg/T": "int32 x\n"})
    (tmp_path / "roschema.toml").write_text('[check.rules]\nRS040 = "warn"\n')
    pkg = write_package(tmp_path, "demo")
    prefix = "tool.roschema." if package_format == "pyproject.toml" else ""
    (pkg / package_format).write_text(f'[{prefix}check.rules]\nRS040 = "off"\n')
    monkeypatch.chdir(pkg)
    result = runner.invoke(app, ["bag-check", str(bag), "--format", "json"])
    assert result.exit_code == 0, result.output
    findings = json.loads(result.stdout)["findings"]
    assert [(f["package"], f["severity"]) for f in findings] == [("other", "warn")]


@pytest.mark.parametrize(
    "definition",
    ["float64 INVALID=nan\n", "float64 x nan\n", "float64[] x [nan, 1.0]\n"],
)
@pytest.mark.parametrize("embedded", [False, True])
def test_mcap_accepts_equivalent_nan_definitions(tmp_path, definition, embedded):
    """Repeated schemas and dependencies may contain equivalent NaN values."""
    bag = tmp_path / "nan.mcap"
    schema = "demo/msg/T"
    text = definition
    if embedded:
        schema = "demo/msg/Wrapper"
        text = "demo/T value\n===\nMSG: demo/T\n" + definition
    _write_bag(bag, [(schema, "ros2msg", text), ("demo/msg/T", "ros2msg", definition)])
    messages = {"T": definition}
    if embedded:
        messages["Wrapper"] = "demo/T value\n"
    pkg = write_package(tmp_path, "demo", msgs=messages)
    result = runner.invoke(app, ["bag-check", str(bag), str(pkg)])
    assert result.exit_code == 0, result.output
