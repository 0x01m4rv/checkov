import logging
from abc import ABC, abstractmethod
import dpath.util
import re

RENDER_REGEX = r'(\$\{([^ ]+)\})'


class DependencyGraph(ABC):

    def __init__(self, root_folder, graph_type, tf_definitions):
        self.logger = logging.getLogger("{}".format(self.__module__))
        self.graph = None
        self.assignments = {}
        self.root_folder = root_folder
        self.tf_definitions = tf_definitions
        self.graph_type = graph_type
        self.block_types_parsers = {
            'variable': self._parse_variable_block,
            'locals': self._parse_locals_block,
            'output': self._parse_outputs_blocks,
            'resource': self._parse_resource_blocks,
            'module': self._parse_module_block
        }

    def _parse_variable_block(self, definition_type, definition_block):
        for variable in definition_block:
            for var_name, values in variable.items():
                if 'default' in values:
                    self.assignments[definition_type][var_name] = values['default'][0]

    def _parse_locals_block(self, definition_type, definition_block):
        self.assignments[definition_type] = definition_block[0]

    def _parse_outputs_blocks(self, definition_type, definition_block):
        for output in definition_block:
            for output_name, values in output.items():
                self.assignments[definition_type][output_name] = values['value'][0]

    def _parse_resource_blocks(self, definition_type, definition_block):
        for resource in definition_block:
            for resource_type, resource_block in resource.items():
                for resource_name, attributes in resource_block.items():
                    self.assignments[definition_type][resource_name] = {}
                    for attribute, value in attributes.items():
                        self.assignments[definition_type][resource_name][attribute] = value[0]

    def _parse_module_block(self, definition_type, definition_block):
        for module in definition_block:
            for module_name, module_values in module.items():
                self.assignments[definition_type][module_name] = module_values

    def _populate_assignments_types(self, tf_definitions):
        for (tf_file, definitions) in tf_definitions.items():
            for (definition_type, definition_block) in definitions.items():
                self.assignments[definition_type] = {}

        for (tf_file, definitions) in tf_definitions.items():
            for (definition_type, definition_block) in definitions.items():
                block_parser = self.block_types_parsers.get(definition_type)
                if block_parser:
                    block_parser(definition_type, definition_block)
                else:
                    continue

    def _assign_definition_value(self, block_type, definition_path, var_value):
        print(block_type, definition_path, var_value)
        definition_expression = dpath.get(self.assignments, "/".join((block_type, *definition_path)))[0]
        rendered_definition = re.sub(RENDER_REGEX, var_value, definition_expression)
        dpath.set(self.assignments, "/".join((block_type, *definition_path)), rendered_definition)

    @abstractmethod
    def compute_dependency_graph(self, root_dir):
        raise NotImplementedError()

    def render_variables(self, tf_definitions):
        self._populate_assignments_types(tf_definitions)
