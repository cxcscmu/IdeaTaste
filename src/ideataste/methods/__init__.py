"""The four methods of the paper. A new method subclasses methods.base.Method and is added here."""

from ideataste.methods.free_topic import Free, Topic
from ideataste.methods.frontier import Frontier
from ideataste.methods.landscape import Landscape

METHOD_CLASSES = {cls.name: cls for cls in (Free, Topic, Landscape, Frontier)}
