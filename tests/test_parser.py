"""Parser and IR tests: every grammar feature plus error cases."""

from __future__ import annotations

import pytest

from roschema.ir import ArrayKind, Constant, Field, SectionKind
from roschema.parser import ParseError, parse_text


def _msg(text: str):
    return parse_text(text, "pkg/msg/T.msg", "pkg", "T", "msg")


def _fields(text: str) -> list[Field]:
    return list(_msg(text).fields())


def test_builtin_scalar_types():
    fields = _fields("bool a\nfloat64 b\nint32 c\nstring d\nwstring e\nbyte f\nchar g\n")
    assert [f.name for f in fields] == ["a", "b", "c", "d", "e", "f", "g"]
    assert all(f.type.is_builtin for f in fields)
    assert all(f.type.array_kind is ArrayKind.NONE for f in fields)


def test_bounded_strings():
    (a, b) = _fields("string<=10 a\nwstring<=5 b\n")
    assert a.type.base == "string" and a.type.string_bound == 10
    assert b.type.base == "wstring" and b.type.string_bound == 5


def test_array_kinds():
    fixed, unbounded, bounded = _fields("float64[3] a\nint32[] b\nuint8[<=4] c\n")
    assert fixed.type.array_kind is ArrayKind.FIXED and fixed.type.array_bound == 3
    assert unbounded.type.array_kind is ArrayKind.UNBOUNDED
    assert bounded.type.array_kind is ArrayKind.BOUNDED and bounded.type.array_bound == 4


def test_bounded_array_of_bounded_string():
    (f,) = _fields("string<=5[<=10] names\n")
    assert f.type.base == "string"
    assert f.type.string_bound == 5
    assert f.type.array_kind is ArrayKind.BOUNDED
    assert f.type.array_bound == 10


def test_namespaced_and_same_package_complex():
    ns, bare = _fields("geometry_msgs/Point p\nHeader h\n")
    assert ns.type.package == "geometry_msgs" and ns.type.base == "Point"
    assert not ns.type.is_builtin
    assert bare.type.package is None and bare.type.base == "Header"
    assert not bare.type.is_builtin


def test_complex_array():
    (f,) = _fields("geometry_msgs/Point[] pts\n")
    assert f.type.package == "geometry_msgs"
    assert f.type.array_kind is ArrayKind.UNBOUNDED


def test_constants_numeric_bool_string():
    consts = list(_msg("int32 X=42\nbool FLAG=true\nstring NAME=hello\n").constants())
    by = {c.name: c for c in consts}
    assert isinstance(by["X"], Constant)
    assert by["X"].value == 42 and by["X"].value_raw == "42"
    assert by["FLAG"].value is True
    assert by["NAME"].value == "hello"


def test_constant_hex_int():
    (c,) = list(_msg("uint32 MASK=0xff\n").constants())
    assert c.value == 255 and c.value_raw == "0xff"


def test_constant_string_value_true_stays_string():
    (c,) = list(_msg("string MODE=true\n").constants())
    assert c.value == "true"


def test_spaced_constant():
    (c,) = list(_msg("int32 X = 5\n").constants())
    assert c.value == 5


def test_field_defaults():
    scalar, arr, quoted = _fields('int32 a 7\nint32[] b [1, 2, 3]\nstring c "hi there"\n')
    assert scalar.default is not None and scalar.default.value == 7
    assert arr.default is not None and arr.default.value == (1, 2, 3)
    assert quoted.default is not None and quoted.default.value == "hi there"
    assert quoted.default.raw == '"hi there"'


def test_string_array_default():
    (f,) = _fields('string[] tags ["a", "b"]\n')
    assert f.default is not None and f.default.value == ("a", "b")


def test_trailing_comment_attached():
    (f,) = _fields("float32 theta  # rotation in radians\n")
    assert f.trailing_comment == "# rotation in radians"


def test_full_line_comment_is_trivia():
    fields = _fields("# leading doc\nint32 a\n# another\nint32 b\n")
    assert [f.name for f in fields] == ["a", "b"]


def test_hash_inside_string_not_a_comment():
    (f,) = _fields('string greeting "hello # world"  # real comment\n')
    assert f.default is not None and f.default.value == "hello # world"
    assert f.trailing_comment == "# real comment"


def test_blank_lines_ignored_but_raw_preserved():
    iface = _msg("int32 a\n\n\nint32 b\n")
    assert [f.name for f in iface.fields()] == ["a", "b"]
    assert "\n\n\n" in iface.raw_text


def test_srv_two_sections():
    iface = parse_text("int32 req\n---\nint32 resp\n", "p/srv/S.srv", "p", "S", "srv")
    assert [s.kind for s in iface.sections] == [SectionKind.REQUEST, SectionKind.RESPONSE]
    assert iface.sections[0].members[0].name == "req"
    assert iface.sections[1].members[0].name == "resp"


def test_action_three_sections_with_empty():
    iface = parse_text(
        "int32 goal\n---\n---\nint32 fb\n", "p/action/A.action", "p", "A", "action"
    )
    kinds = [s.kind for s in iface.sections]
    assert kinds == [SectionKind.GOAL, SectionKind.RESULT, SectionKind.FEEDBACK]
    assert iface.sections[1].members == ()  # empty result section is legal
    assert iface.sections[2].members[0].name == "fb"


def test_interface_key():
    iface = parse_text("int32 a\n---\nint32 b\n", "p/srv/S.srv", "my_pkg", "Do", "srv")
    assert iface.key == "my_pkg/srv/Do"


def test_type_render_roundtrip():
    srcs = [
        "float64[3]",
        "int32[]",
        "uint8[<=4]",
        "string<=10",
        "string<=5[<=10]",
        "geometry_msgs/Point[]",
    ]
    for src in srcs:
        (f,) = _fields(f"{src} a\n")
        assert f.type.render() == src


# --- error cases ---


def test_error_wrong_separator_count_for_msg():
    with pytest.raises(ParseError) as e:
        _msg("int32 a\n---\nint32 b\n")
    assert "separator" in e.value.message


def test_error_missing_name():
    with pytest.raises(ParseError) as e:
        _msg("int32\n")
    assert "name" in e.value.message


def test_error_malformed_array():
    with pytest.raises(ParseError) as e:
        _msg("int32[ a\n")
    assert "array" in e.value.message


def test_error_invalid_namespaced_type():
    with pytest.raises(ParseError):
        _msg("pkg//Type a\n")


def test_error_constant_missing_value():
    with pytest.raises(ParseError) as e:
        _msg("int32 X=\n")
    assert "value" in e.value.message


def test_error_render_has_caret():
    with pytest.raises(ParseError) as e:
        _msg("int32[ a\n")
    rendered = e.value.render()
    assert "^" in rendered
    assert "T.msg:1:" in rendered
