"""
Copyright 2008, 2009, 2010 Free Software Foundation, Inc.
This file is part of GNU Radio

GNU Radio Companion is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

GNU Radio Companion is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA
"""

import os
import subprocess
import tempfile
from Cheetah.Template import Template
import expr_utils
from Constants import \
	TOP_BLOCK_FILE_MODE, HIER_BLOCK_FILE_MODE, \
	HIER_BLOCKS_LIB_DIR, PYEXEC, \
	FLOW_GRAPH_TEMPLATE
import convert_hier
from .. gui import Messages

class Generator(object):

	def __init__(self, flow_graph, file_path):
		"""
		Initialize the generator object.
		Determine the file to generate.
		@param flow_graph the flow graph object
		@param file_path the path to write the file to
		"""
		self._flow_graph = flow_graph
		self._generate_options = self._flow_graph.get_option('generate_options')
		if self._generate_options == 'hb':
			self._mode = HIER_BLOCK_FILE_MODE
			dirname = HIER_BLOCKS_LIB_DIR
		else:
			self._mode = TOP_BLOCK_FILE_MODE
			dirname = os.path.dirname(file_path)
			#handle the case where the directory is read-only
			#in this case, use the system's temp directory
			if not os.access(dirname, os.W_OK):
				dirname = tempfile.gettempdir()
		filename = self._flow_graph.get_option('id') + '.py'
		self._file_path = os.path.join(dirname, filename)

	def get_file_path(self): return self._file_path

	def write(self):
		#do throttle warning
		all_keys = ' '.join(map(lambda b: b.get_key(), self._flow_graph.get_enabled_blocks()))
		if ('usrp' not in all_keys) and ('audio' not in all_keys) and ('throttle' not in all_keys) and self._generate_options != 'hb':
			Messages.send_warning('''\
This flow graph may not have flow control: no audio or usrp blocks found. \
Add a Misc->Throttle block to your flow graph to avoid CPU congestion.''')
		#generate
		open(self.get_file_path(), 'w').write(str(self))
		if self._generate_options == 'hb':
			#convert hier block to xml wrapper
			convert_hier.convert_hier(self._flow_graph, self.get_file_path())
		os.chmod(self.get_file_path(), self._mode)

	def get_popen(self):
		"""
		Execute this python flow graph.
		@return a popen object
		"""
		#execute
		cmds = [PYEXEC, '-u', self.get_file_path()] #-u is unbuffered stdio
		if self._generate_options == 'no_gui':
			cmds = ['xterm', '-e'] + cmds
		p = subprocess.Popen(args=cmds, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, universal_newlines=True)
		return p

	def __str__(self):
		"""
		Convert the flow graph to python code.
		@return a string of python code
		"""
		title = self._flow_graph.get_option('title') or self._flow_graph.get_option('id').replace('_', ' ').title()
		imports = self._flow_graph.get_imports()
		variables = self._flow_graph.get_variables()
		parameters = self._flow_graph.get_parameters()
		#list of variables with controls
		controls = filter(lambda v: v.get_make(), variables)
		#list of blocks not including variables and imports and parameters and disabled
		blocks = sorted(self._flow_graph.get_enabled_blocks(), lambda x, y: cmp(x.get_id(), y.get_id()))
		probes = filter(lambda b: b.get_key().startswith('probe_'), blocks) #ensure probes are last in the block list
		#get a list of notebooks and sort them according dependencies
		notebooks = expr_utils.sort_objects(
			filter(lambda b: b.get_key() == 'notebook', blocks),
			lambda n: n.get_id(), lambda n: n.get_param('notebook').get_value(),
		)
		#list of regular blocks (all blocks minus the special ones)
		blocks = filter(lambda b: b not in (imports + parameters + variables + probes + notebooks), blocks) + probes
		#list of connections where each endpoint is enabled
		connections = filter(lambda c: not c.is_msg(), self._flow_graph.get_enabled_connections())
		messages = filter(lambda c: c.is_msg(), self._flow_graph.get_enabled_connections())
		#list of variable names
		var_ids = [var.get_id() for var in parameters + variables]
		#prepend self.
		replace_dict = dict([(var_id, 'self.%s'%var_id) for var_id in var_ids])
		#list of callbacks
		callbacks = [
			expr_utils.expr_replace(cb, replace_dict)
			for cb in sum([block.get_callbacks() for block in self._flow_graph.get_enabled_blocks()], [])
		]
		#map var id to callbacks
		var_id2cbs = dict(
			[(var_id, filter(lambda c: expr_utils.get_variable_dependencies(c, [var_id]), callbacks))
			for var_id in var_ids]
		)
		#load the namespace
		namespace = {
			'title': title,
			'imports': imports,
			'flow_graph': self._flow_graph,
			'variables': variables,
			'notebooks': notebooks,
			'controls': controls,
			'parameters': parameters,
			'blocks': blocks,
			'connections': connections,
			'messages': messages,
			'generate_options': self._generate_options,
			'var_id2cbs': var_id2cbs,
		}
		#build the template
		t = Template(open(FLOW_GRAPH_TEMPLATE, 'r').read(), namespace)
		return str(t)
