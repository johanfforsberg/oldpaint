build:
	git submodule init
	git submodule update
	fogl/bin/get_pyglet.sh
	python3 -m venv env
	env/bin/pip install cython euclid3 imgui pypng xdg pluginbase
	env/bin/pip install -e ./pyglet
	env/bin/pip install -e ./fogl

run:
	env/bin/python -m oldpaint
