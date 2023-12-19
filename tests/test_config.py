from collections import OrderedDict
from pathlib import Path
from typing import Iterator
import os

import pytest

from labgrid.config import Config
from labgrid.exceptions import InvalidConfigError

def test_get_target_option(tmpdir):
    p = tmpdir.join("config.yaml")
    p.write(
        """
        targets:
          main:
            options:
              str: test
              list: [1, 2, 3]
              dict:
                a: 1
                b: 2
              bool: False
              int: 0x20
              float: 3.14
              none: null
        """
    )
    c = Config(str(p))
    assert c.get_target_option("main", "str") == "test"
    assert c.get_target_option("main", "list") == [1, 2, 3]
    assert c.get_target_option("main", "dict") == OrderedDict([('a', 1), ('b', 2)])
    assert c.get_target_option("main", "bool") is False
    assert c.get_target_option("main", "int") == 0x20
    assert c.get_target_option("main", "float") == 3.14
    assert c.get_target_option("main", "none") is None

    with pytest.raises(KeyError) as err:
        c.get_target_option("main", "blah")
    assert "No option" in str(err)

    with pytest.raises(KeyError) as err:
        c.get_target_option("nonexist", "str")
    assert "No target" in str(err)

def test_set_target_option(tmpdir):
    p = tmpdir.join("config.yaml")
    p.write(
        """
        targets:
          main:
        """
    )
    c = Config(str(p))

    with pytest.raises(KeyError) as err:
        c.get_target_option("main", "spam")
    assert "No option" in str(err)

    c.set_target_option("main", "spam", "eggs")
    assert c.get_target_option("main", "spam") == "eggs"

    obj = object()
    c.set_target_option("main", "obj", obj)
    assert c.get_target_option("main", "obj") is obj

def test_template(tmpdir):
    p = tmpdir.join("config.yaml")
    p.write(
        """
        dict:
          list:
          - a
          - b
          - !template $BASE
          string: !template ${BASE}/suffix
        """
    )
    c = Config(str(p))
    assert 'a' in c.data['dict']['list']
    assert c.data['dict']['list'][2] == str(tmpdir)
    assert c.data['dict']['string'] == str(tmpdir)+'/suffix'

def test_template_bad_placeholder(tmpdir):
    p = tmpdir.join("config.yaml")
    p.write(
        """
        string: !template $
        """
    )
    with pytest.raises(InvalidConfigError) as excinfo:
        Config(str(p))
    assert "is invalid" in excinfo.value.msg
    assert "template string" in excinfo.value.msg

def test_template_bad_key(tmpdir):
    p = tmpdir.join("config.yaml")
    p.write(
        """
        string: !template ${INVALID}
        """
    )
    with pytest.raises(InvalidConfigError) as excinfo:
        Config(str(p))
    assert "unknown variable" in excinfo.value.msg

def test_tool(tmpdir):
    t = tmpdir.join("testtool")
    t.write("content")
    p = tmpdir.join("config.yaml")
    p.write(
        """
        tools:
          testtool: {}
        """.format(t)
    )
    c = Config(str(p))

    assert c.get_tool("testtool") == t

def test_tool_no_explicit_tool(tmpdir):
    t = tmpdir.join("testtool")
    t.write("content")
    p = tmpdir.join("config.yaml")
    p.write(
        """
        dict: {}
        """
    )
    c = Config(str(p))

    assert c.get_tool("testtool") == "testtool"

def test_include(tmp_path: Path) -> None:
    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
includes:
  - !include first.yaml
  - !include second.yaml
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""
first:
  - a
  - b
  - c
""")

    second_yaml = tmp_path / "configs" / "second.yaml"
    second_yaml.write_text("""
second:
  foo: bar
""")

    c = Config(str(config_yaml.resolve()))
    assert 'b' in c.data['first']
    assert c.data['second']['foo'] == 'bar'

@pytest.fixture(scope="function")
def include_env() -> Iterator[None]:
    os.environ['LG_FIRST'] = 'first.yaml'
    os.environ['LG_SECOND'] = 'second.yaml'
    os.environ['LG_THIRD'] = 'third'
    os.environ['LG_FOO'] = 'bar'
    yield
    del os.environ['LG_FOO']
    del os.environ['LG_THIRD']
    del os.environ['LG_SECOND']
    del os.environ['LG_FIRST']

def test_include_inline(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
  subnode: !include first.yaml
  another: !include second.yaml
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""---
first:
  - a
  - b
  - c
""")

    second_yaml = tmp_path / "configs" / "second.yaml"
    second_yaml.write_text("""---
foo: !template ${LG_FOO}
""")

    c = Config(str(config_yaml.resolve()))
    assert 'a' in c.data['target']['subnode']['first']
    assert c.data['target']['another']['foo'] == 'bar'

def test_include_inline_var(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
  subnode: !include ${LG_FIRST}
  another: !include $LG_SECOND
  yetanother: !include ${LG_THIRD}.yaml
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""---
first:
  - a
  - b
  - c
""")

    second_yaml = tmp_path / "configs" / "second.yaml"
    second_yaml.write_text("""---
foo: !template ${LG_FOO}
""")

    third_yaml = tmp_path / "configs" / "third.yaml"
    third_yaml.write_text("""---
hello: world
""")

    c = Config(str(config_yaml.resolve()))
    assert 'a' in c.data['target']['subnode']['first']
    assert c.data['target']['another']['foo'] == 'bar'
    assert c.data['target']['yetanother']['hello'] == 'world'

def test_include_inline_var_doesnotexist(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
  subnode: !include ${LG_DOESNOTEXIST}
  another: !include ${LG_FIRST}
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""---
first:
  - a
  - b
  - c
""")

    with pytest.raises(InvalidConfigError) as excinfo:
        Config(str(config_yaml.resolve()))
    assert 'Could not resolve key' in excinfo.value.msg

def test_include_var(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
includes:
  - !include ${LG_FIRST}
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""
first:
  - a
  - b
  - c
""")

    c = Config(str(config_yaml.resolve()))
    assert 'b' in c.data['first']

def test_include_template(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
includes:
  - !include first.yaml
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""
first:
  - foo
  - !template ${LG_FOO}
  - baz
""")

    c = Config(str(config_yaml.resolve()))
    assert 'bar' in c.data['first']

def test_include_template_bad_placeholder(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
includes:
  - !include first.yaml
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""
first:
  - foo
  - !template $
  - baz
""")

    with pytest.raises(InvalidConfigError) as excinfo:
        Config(str(config_yaml.resolve()))
    assert "is invalid" in excinfo.value.msg
    assert "template string" in excinfo.value.msg

def test_include_template_bad_key(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
includes:
  - !include first.yaml
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""
first:
  - foo
  - !template ${LG_DOESNOTEXIST}
  - baz
""")

    with pytest.raises(InvalidConfigError) as excinfo:
        Config(str(config_yaml.resolve()))
    assert 'refers to unknown variable' in excinfo.value.msg

def test_include_template_var(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
includes:
  - !include ${LG_FIRST}
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""
first:
  - foo
  - !template ${LG_FOO}
  - baz
""")

    c = Config(str(config_yaml.resolve()))
    assert 'bar' in c.data['first']

def test_include_template_var_bad_placeholder(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
includes:
  - !include ${LG_FIRST}
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""
first:
  - foo
  - !template $
  - baz
""")

    with pytest.raises(InvalidConfigError) as excinfo:
        Config(str(config_yaml.resolve()))
    assert "is invalid" in excinfo.value.msg
    assert "template string" in excinfo.value.msg

def test_include_template_var_bad_key(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
includes:
  - !include ${LG_FIRST}
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""
first:
  - foo
  - !template ${LG_DOESNOTEXIST}
  - baz
""")

    with pytest.raises(InvalidConfigError) as excinfo:
        Config(str(config_yaml.resolve()))
    assert "refers to unknown variable" in excinfo.value.msg

def test_include_template_var_doesnotexist(tmp_path: Path, include_env: None) -> None:
    del include_env  # unused

    config_yaml = tmp_path / "configs" / "config.yaml"
    config_yaml.parent.mkdir(parents=True, exist_ok=True)
    config_yaml.write_text("""---
target:
  main:
    drivers: {}
includes:
  - !include first.yaml
  - !include ${LG_DOESNOTEXIST}second.yaml
""")
    first_yaml = tmp_path / "configs" / "first.yaml"
    first_yaml.write_text("""
first:
  - foo
  - bar
  - baz
""")
    second_yaml = tmp_path / "configs" / "second.yaml"
    second_yaml.write_text("""
second:
  foo: bar
""")


    with pytest.raises(InvalidConfigError) as excinfo:
        Config(str(config_yaml.resolve()))
    assert "Could not resolve key" in excinfo.value.msg
