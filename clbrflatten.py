"""This is trying to hack goto-definition(F3) feature in Eclipse for IDLE Python.
   Although it is sometimes not performance good, it is practically useful. --
   Especially when exploring third party source packages but without needing
   to startup and running the heavy Eclipse.
   
   It grabs the selection text from IDLE and return (filename, lineno) in
   which the text is defined, be it a package, module, class, function, method, or
   global data, to IDLE for displaying. Ignore or show info in status bar if
   failed to find such definition, or if it is a builtin function or method.
"""
import sys
import re
import os.path
import types
import pyclbr
import imp

def clbrflatten(module):
    """Flatten the class hierarch returned by pyclbr.
        Note that currently pyclbr seems only to browse classes, functions
        and methods defined in current module plus super classes. For classes,
        functions and methods in external module, we are trying to use eval in
        current namespace to deduce file and lineno info. See gotodef below.
        """

    dirname = ''
    if module[-3:] == '.py':
        dirname, basename = os.path.split(module)
        module, ext = os.path.splitext(basename)

    cd = pyclbr.readmodule_ex(module, dirname)

    classes = cd.items()
    clsnames = cd.keys()
    for clsname, cls in classes: 
        # it is a class, not function or string
        if type(cls) == types.InstanceType and hasattr(cls, 'super'):
            for supercls in cls.super:
                # in case superclass could not be resolved, it is a string
                if (type(supercls) == types.InstanceType
                    and supercls.name not in clsnames): 
                    classes.append((supercls.name, supercls))
                    clsnames.append(supercls.name)

    return dict(classes)

def gotodef(token, module):
    """for token in module(name),
        return file and lineno in which the token is defined.
        the token would be module(package), class, function, method,
        and hopefully the global data appeared in the module(name)

        First try classes from clbrflatten, then eval and file grep/match for
        external classes, functions or methods, last try file grep/match for
        global data using modulefinder

        If failed to find, or builtin funtions or methods, ignore or raise
        NameError, ImportError, or KeyError
        """

    dirname = ''
    if module[-3:] == '.py':
        dirname, basename = os.path.split(module)
        module, ext = os.path.splitext(basename)
        
    # deal with packages, e.g. django.contrib.admin
    # this is the case eval can not deal without first import the package. You
    # can do imp.find_module and imp.load_module for each subpackage, then eval
    # with sys.modules. Here just for convenience hack.
    # However this technique can not deal with the case 'os.path' --> ntpath.
    # So both this technique and eval are needed.
    try:
        classes = clbrflatten(token)
        if '__path__' in classes:
            filename = os.path.join(classes['__path__'][0], '__init__.py')
            return (filename, 1)
    except (NameError, ImportError, KeyError), msg:
        pass
        
    try:
        # TODO: try-except clauses
        f, filename, desc = imp.find_module(module)
        mod = imp.load_module(module, f, filename, desc)

        namespace = sys.modules.copy()
        namespace.update(mod.__dict__)
        # TODO: try-except clauses
        value = eval(token, namespace)      # deal with os.path, etc.
        if hasattr(value, '__name__'):
            token = value.__name__
        else:
            token = token.split('.')[-1]

        # First try clbrflatten
        classes = clbrflatten(module)
        if token in classes:    # class or function in the module
            return (classes[token].file, classes[token].lineno)
        else:   # look for methods for all classes in the module
            for cls in classes:
                if hasattr(classes[cls], 'methods'):
                    for method, lineno in classes[cls].methods.iteritems():
                        if token == method:
                            return (classes[cls].file, lineno)

        # Then try eval and file grep/match
        if type(value) == types.FunctionType:
            filename = value.func_globals['__file__']
            name, ext = os.path.splitext(filename)
            filename = name + '.py'
            funcname = value.__name__
            f = open(filename)
            pattern = re.compile('^[ \t]*def[ \t]*'
                                 + funcname + '[ \t]*\(.*\).*$')
            return getlineno(f, filename, pattern)
            
        elif type(value) == types.MethodType:
            modname = value.im_class.__module__
            f, filename, desc = imp.find_module(modname)
            methodname = value.__name__
            pattern = re.compile('^[ \t]*def[ \t]*'
                                 + methodname + '[ \t]*\(.*\).*$')
            return getlineno(f, filename, pattern)
        
        elif type(value) == types.ModuleType:
            # module or package,
            # for package, __init__.py automatically appended by eval
            filename, ext = os.path.splitext(value.__file__)
            filename = filename + '.py'         # in case '.pyc'
            return (filename, 1)

        elif (type(value) == types.BuiltinFunctionType
                or type(value) == types.BuiltinMethodType):
            return ('Builtin Function or Method or Type', 0)

        # Accommodate new-style class and classic class, and their instances
        elif (type(value) == types.ClassType
                or type(value) == types.TypeType
                or type(value) == types.InstanceType
                or (type(value) != types.TypeType
                      and type(type(value)) == types.TypeType
                      and hasattr(value, '__module__'))):
                    # this is function, method, module, an instance of new-style class.
                    # function, method, module are already filtered up above, so
                    # it is an instance of new-style class, or any thing else left?
            
            if (type(value) == types.ClassType
                or type(value) == types.TypeType):
                cls = value
            elif (type(value) == types.InstanceType
                    or (type(value) != types.TypeType
                          and type(type(value)) == types.TypeType
                          and hasattr(value, '__module__'))):
                cls = value.__class__
            modname = cls.__module__
            f, filename, desc = imp.find_module(modname)
            if f is None:
                return ('Builtin Function or Method or Type', 0)
            
            pattern = re.compile('^[ \t]*class[ \t]*'
                                 + cls.__name__ + '[ \t]*\(?.*\)?[ \t]*:$')
            return getlineno(f, filename, pattern)

        else:
            # global data
            # good guess by matching assignment leftside, just for convenience
            # It is ok for purpose without hurt
            pattern = re.compile('^[ \t]*' + token + '[ \t]*=[ \t]*.*$')
            if token in mod.__dict__:   # current file
                return getlineno(f, filename, pattern)
            else:
                # otherwise, the first match in imported modules
                # using modulefinder  
                from modulefinder import ModuleFinder
                finder=ModuleFinder()
                finder.run_script(filename)
                modules = finder.modules.itervalues()
                files = [m.__file__ for m in modules if m.__file__ is not None]
                import fileinput
                for line in fileinput.input(files):
                    if pattern.match(line):
                        return (fileinput.filename(), fileinput.filelineno())
                    
    except (NameError, ImportError, KeyError), msg:
        raise
    finally:
        if f:
            f.close()

def getlineno(f, filename, pattern):
    for lineno, line in enumerate(f.readlines()):
        if pattern.match(line):
            return (filename, lineno)

def test():
    print gotodef('os.path', 'clbrtest')
    print gotodef('os', 'clbrtest')
    print gotodef('EditorWindow', 'clbrtest')
    print gotodef('EditorWindow.EditorWindow', 'clbrtest')
    print gotodef('EditorWindow.EditorWindow.goto_definition', 'clbrtest')
    print gotodef('EditorWindow.keynames', 'clbrtest')
    print gotodef('django.contrib.admin', 'clbrtest')
    print gotodef('django.contrib', 'clbrtest')
    print gotodef('django', 'clbrtest')

if __name__ == '__main__':
    test()
    
    
