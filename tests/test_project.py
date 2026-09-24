"""Tests for reading the project file into products and resources."""

from __future__ import annotations

import pytest

from custom_components.lk_ihc.catalog import ResourceRole, icon_for, model_name, role_for
from custom_components.lk_ihc.project import Project, parse_project

from .conftest import load_project


@pytest.fixture
def project():
    """The parsed test project."""
    return parse_project(load_project())


def test_products_and_groups(project):
    """Every product in the file is found, with its group, position and model name."""
    assert [group for group in project.groups] == ["Living room", "Utility room"]
    assert len(project.products) == 9
    lamp = next(p for p in project.products if p.product_id == 0x2001)
    assert lamp.group == "Living room"
    assert lamp.device_name == "Lamp outlet (in the ceiling)"
    assert lamp.model == "Dataline lamp outlet"
    assert lamp.model_id == "0x2202"


def test_roles(project):
    """Each resource becomes what its product says it is."""
    roles = {resource.ihc_id: resource.role for _product, resource in project.resources}
    assert roles[0x3001] is ResourceRole.LIGHT  # lamp outlet output
    assert roles[0x3002] is ResourceRole.LIGHT  # dimmer output
    assert roles[0x3003] is ResourceRole.BUTTON  # a key on the combi dimmer
    assert roles[0x3005] is ResourceRole.BUTTON  # a key on the wall switch
    assert roles[0x3007] is ResourceRole.SWITCH  # universal relay
    assert roles[0x3008] is ResourceRole.BINARY_SENSOR  # PIR movement
    assert roles[0x300B] is ResourceRole.SENSOR  # temperature


def test_dimmable_and_device_classes(project):
    """A dimmer can dim, a plain outlet cannot, and sensors carry their device class."""
    by_id = {resource.ihc_id: resource for _product, resource in project.resources}
    assert by_id[0x3002].dimmable is True
    assert by_id[0x3001].dimmable is False
    assert by_id[0x3008].device_class == "motion"
    assert by_id[0x300B].device_class == "temperature"


def test_settings_and_extra_inputs_are_not_exposed(project):
    """A setting node is skipped, and a PIR's second contact is created disabled."""
    ids = {resource.ihc_id for _product, resource in project.resources}
    assert 0x300A not in ids  # setting="yes"
    by_id = {resource.ihc_id: resource for _product, resource in project.resources}
    assert by_id[0x3008].enabled_default is True
    assert by_id[0x3009].enabled_default is False


def test_unknown_product_still_usable(project):
    """An unknown product keeps its output as a switch and its input as a disabled sensor."""
    by_id = {resource.ihc_id: resource for _product, resource in project.resources}
    assert by_id[0x300C].role is ResourceRole.SWITCH
    assert by_id[0x300D].role is ResourceRole.BINARY_SENSOR
    assert by_id[0x300D].enabled_default is False
    unknown = next(p for p in project.products if p.identifier == "_0x9999")
    assert unknown.model == "Something unknown"  # the product's own name, when the catalogue has none
    assert unknown.model_id == "0x9999"


def test_counts(project):
    """The summary counts every role, which is what the setup log and diagnostics show."""
    assert parse_project(load_project()).counts() == {
        "light": 2,
        "button": 5,
        "switch": 3,
        "binary_sensor": 3,
        "sensor": 1,
    }


def test_catalog_helpers():
    """Model names come from the catalogue, and an unknown identifier falls back."""
    assert model_name("_0x2101", "fallback") == "Dataline wall switch, 2 keys"
    assert model_name("_0x9999", "fallback") == "fallback"
    assert role_for("_0x9999", "airlink_dimming", 1).dimmable is True


def test_icons(project):
    """Keys and relays get an icon; lights and sensors keep the one their device class gives them."""
    by_id = {resource.ihc_id: resource for _product, resource in project.resources}
    assert by_id[0x3005].icon == "mdi:gesture-tap-button"  # a key
    assert by_id[0x3007].icon == "mdi:electric-switch"  # a relay
    assert by_id[0x3001].icon is None  # a light
    assert by_id[0x3008].icon is None  # a PIR
    assert icon_for("_0x4201", ResourceRole.SWITCH) == "mdi:power-socket"  # a plug outlet


RS485_LED_DIMMER = """
<utcs><groups><group id="_0x1001" name="Dining room">
  <product_rs485_led_dimmer id="_0x2001" product_identifier="_0x4409" name="IHC LED Dimmer 2 channels"
                            position="Ceiling spots (dining and reading room)">
    <resource_flag id="_0x3001" name="Channel synchronisation"/>
    <rs485_led_dimmer_channel id="_0x2002" product_identifier="_0x4410" name="LED Dimmer channel 1 (Dining room)"
                              position="">
      <airlink_dimmer_increase id="_0x3002" name="On / dim up"/>
      <airlink_dimmer_decrease id="_0x3003" name="Off / dim down"/>
      <airlink_dimming id="_0x3004" name="Light level"/>
      <light_indication id="_0x3005" name="Light indication"/>
      <dimmer_settings id="_0x3006"><dimmer_setting_minimum_value id="_0x3007"/></dimmer_settings>
    </rs485_led_dimmer_channel>
    <rs485_led_dimmer_channel id="_0x2003" product_identifier="_0x4410" name="LED Dimmer channel 2 (Reading room)"
                              position="">
      <airlink_dimming id="_0x3008" name="Light level"/>
    </rs485_led_dimmer_channel>
  </product_rs485_led_dimmer>
</group></groups></utcs>
"""


def test_rs485_led_dimmer_channels_are_dimmable_lights():
    """Each channel of an RS485 LED dimmer module is a product with one dimmable light.

    The module is only the box: the channels carry the product identifier (_0x4410), the name and
    the light level, and each one often lights a room of its own.
    """
    project = parse_project(RS485_LED_DIMMER)
    assert [product.product_id for product in project.products] == [0x2002, 0x2003]
    channel = project.products[0]
    assert channel.device_name == "LED Dimmer channel 1 (Dining room)"
    assert channel.model == "RS485 LED dimmer channel"
    assert channel.group == "Dining room"
    assert [resource.ihc_id for resource in channel.resources] == [0x3004]
    light = channel.resources[0]
    assert light.role is ResourceRole.LIGHT
    assert light.dimmable is True
    assert [resource.ihc_id for resource in project.products[1].resources] == [0x3008]


def test_project_without_products():
    """A file with nothing in it parses to an empty project rather than failing."""
    project = parse_project("<utcs><groups><group name='Empty'/></groups></utcs>")
    assert project.products == []
    assert project.counts() == {}


def test_function_blocks_are_read(project: Project) -> None:
    """The controller's own logic is part of the project and worth knowing about."""
    assert len(project.function_blocks) == 1
    block = project.function_blocks[0]
    assert block.name == "1.1.01. Toggle block with on, off and timer"
    # The catalogue number is how IHC files the block, not how anyone refers to it.
    assert block.short_name == "Toggle block with on, off and timer"


def test_wiring_names_what_drives_a_product(project: Project) -> None:
    """A relay fed through a function block reports the switch, with the block as the reason."""
    # The fixture holds two relays; this is the one the link chain reaches.
    relay = next(product for product in project.products if product.position == "in the attic")
    assert relay.controlled_by == ("Wall switch 2 keys (by the hall door)",)
    assert relay.function_blocks == ("Toggle block with on, off and timer",)


def test_wiring_is_empty_when_nothing_links(project: Project) -> None:
    """A product no link reaches says nothing rather than guessing."""
    sensor = next(product for product in project.products if product.name == "Temperature sensor")
    assert sensor.controlled_by == ()
    assert sensor.function_blocks == ()


def test_logic_reads_flags_and_enums() -> None:
    """Flags and enums are logic resources, not tied to any product."""
    from custom_components.lk_ihc.logic import parse_logic

    from .conftest import load_project

    logic = parse_logic(load_project())
    assert [flag.name for flag in logic.flags] == ["Holiday flag"]
    enum = next(e for e in logic.enums if e.name == "Light mode")
    # Options come from the shared definition the enum points at by typedef.
    assert enum.options == ("Auto", "Manual")
    assert enum.kind == "enum"


def test_values_written_in_a_program_are_not_logic() -> None:
    """A program's conditions and actions hold enum values as resources; only the block's own count."""
    from custom_components.lk_ihc.logic import parse_logic

    logic = parse_logic(
        """<utcs><groups><group name="Hall">
          <functionblock id="_0x100" name="Dimmer block">
            <settings><resource_enum id="_0x101" name="Start level" typedef="_0x900"/></settings>
            <outputs><resource_enum id="_0x102" name="Dimmer status" typedef="_0x900"/></outputs>
            <programs><program_simple name="Program"><actions>
              <action><resource_enum id="_0x103" name="Enumerator" typedef="_0x900"/></action>
              <program_case name="Case">
                <case_action><resource_enum id="_0x104" typedef="_0x900"/></case_action>
              </program_case>
            </actions></program_simple></programs>
          </functionblock>
        </group></groups></utcs>"""
    )
    assert [enum.name for enum in logic.enums] == ["Start level", "Dimmer status"]
