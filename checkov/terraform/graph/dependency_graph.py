import logging
from abc import ABC, abstractmethod
import dpath.util
import re
import os

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
            'provider': self._parse_provider_block,
            'variable': self._parse_variable_block,
            'locals': self._parse_locals_block,
            'output': self._parse_outputs_blocks,
            'resource': self._parse_resource_blocks,
            'module': self._parse_module_block
        }

    def _parse_provider_block(self, tf_file, definition_type, definition_block):
        for provider_name, provider_block in definition_block[0].items():
            for attribute_name, value in provider_block.items():
                dpath.new(self.assignments[tf_file], "/".join([definition_type, attribute_name]), value[0])

    def _parse_variable_block(self, tf_file, definition_type, definition_block):
        for variable in definition_block:
            for var_name, values in variable.items():
                if 'default' in values:
                    dpath.new(self.assignments[tf_file], "/".join([definition_type, var_name]), values['default'][0])

    def _parse_locals_block(self, tf_file, definition_type, definition_block):
        for local_name, value in definition_block[0].items():
            dpath.new(self.assignments[tf_file], "/".join([definition_type, local_name]), value[0])

    def _parse_outputs_blocks(self, tf_file, definition_type, definition_block):
        for output in definition_block:
            for output_name, values in output.items():
                dpath.new(self.assignments[tf_file], "/".join([definition_type, output_name]), values['value'][0])

    def _parse_resource_attributes(self, attributes, tf_file, definition_type, resource_type, resource_name,
                                   subpath_acc):
        for attribute, value_fetch in attributes.items():
            attribute_path = "/".join([definition_type, resource_type, resource_name,
                                       os.path.join(subpath_acc, attribute)])

            if isinstance(value_fetch, dict):
                self._parse_resource_attributes(value_fetch, tf_file, definition_type, resource_type, resource_name,
                                                os.path.join(subpath_acc, attribute))
            elif isinstance(value_fetch, list):
                value = value_fetch[0]
                if isinstance(value, dict):
                    self._parse_resource_attributes(value, tf_file, definition_type, resource_type, resource_name,
                                                    os.path.join(subpath_acc, attribute))
                else:
                    dpath.new(self.assignments[tf_file],
                              attribute_path,
                              value)
            else:
                dpath.new(self.assignments[tf_file],
                          attribute_path,
                          value_fetch)

    def _parse_resource_blocks(self, tf_file, definition_type, definition_block):
        for resource in definition_block:
            for resource_type, resource_block in resource.items():
                for resource_name, attributes in resource_block.items():
                    self._parse_resource_attributes(attributes, tf_file, definition_type, resource_type, resource_name,
                                                    '')

    def _populate_files_vars(self):
        curr_cwd = os.getcwd()
        for tf_file, definition_types in self.assignments.items():
            file_folder = os.path.split(tf_file)[0]
            os.chdir(file_folder)
            for file in [name for name in os.listdir(os.getcwd()) if name.endswith('.tf')]:
                full_file_path = os.path.join(file_folder, file)
                input_variables = self.assignments[full_file_path].get('variable')
                if input_variables and not self.assignments[tf_file].get('variable'):
                    self.assignments[tf_file]['var'] = input_variables
        os.chdir(curr_cwd)

    def _populate_modules_outputs(self):
        curr_cwd = os.getcwd()
        for tf_file, definition_types in self.assignments.items():
            if definition_types.get('module'):
                for module_name, module_values in definition_types['module'].items():
                    module_source = module_values['var']['source']
                    module_folder = os.path.split(tf_file)[0]
                    os.chdir(module_folder)
                    os.chdir(os.path.abspath(module_source))
                    for file in [name for name in os.listdir(os.getcwd()) if name.endswith('.tf')]:
                        output_file = os.path.join(os.path.join(module_folder, module_source), file)
                        output_values = self.assignments[output_file].get('output')
                        if output_values:
                            dpath.new(self.assignments[tf_file], "/".join(['module', module_name, 'output']),
                                      output_values)
        os.chdir(curr_cwd)

    def _parse_module_block(self, tf_file, definition_type, definition_block):
        for module in definition_block:
            for module_name, module_values in module.items():
                for key, value in module_values.items():
                    dpath.new(self.assignments[tf_file], "/".join([definition_type, module_name, 'var', key]), value[0])

    def _populate_definitions_assignments(self):
        for (tf_file, definitions) in self.tf_definitions.items():
            self.assignments[tf_file] = {}
            for (definition_type, definition_block) in definitions.items():
                self.assignments[tf_file][definition_type] = {}

        for (tf_file, definitions) in self.tf_definitions.items():
            for (definition_type, definition_block) in definitions.items():
                block_parser = self.block_types_parsers.get(definition_type)
                if block_parser:
                    block_parser(tf_file, definition_type, definition_block)
                else:
                    continue

        self._populate_modules_outputs()
        self._populate_files_vars()

    def _assign_definition_value(self, block_type, definition_path, var_value):
        print(block_type, definition_path, var_value)
        definition_expression = dpath.get(self.assignments, "/".join((block_type, *definition_path)))[0]
        rendered_definition = re.sub(RENDER_REGEX, var_value, definition_expression)
        dpath.set(self.assignments, "/".join((block_type, *definition_path)), rendered_definition)

    def compute_dependency_graph(self, root_dir):
        self._populate_definitions_assignments()

    @abstractmethod
    def render_variables(self, tf_file):
        raise NotImplementedError()
