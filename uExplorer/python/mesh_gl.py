"""Compatibility OpenGL depth-buffered diagnostic mesh canvas.

Uses only the platform OpenGL implementation, never game libraries.
"""
import ctypes
import ctypes.util
import sys
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from mesh_decode import project
from material_state import BLENDS,render_order


class GLCanvas(QOpenGLWidget):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.ids={};self.source=None;self.gl=None
        self.layer_ids={};self.fragment_program=None;self.fragment_failed=False
        format=QSurfaceFormat();format.setVersion(2,1)
        format.setProfile(QSurfaceFormat.CompatibilityProfile)
        format.setDepthBufferSize(24);format.setAlphaBufferSize(8)
        self.setFormat(format)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def showEvent(self,event):
        super().showEvent(event)
        QTimer.singleShot(250,self.check_context)

    def check_context(self):
        if self.isVisible() and not self.isValid():
            self.owner.gpu_failed=True;self.hide()
            self.owner.graphicsUnavailable.emit('OpenGL недоступен: используется диагностический Qt raster без z-buffer')
            self.owner.update()

    def initializeGL(self):
        library=ctypes.WinDLL('opengl32.dll') if sys.platform=='win32' else ctypes.CDLL(ctypes.util.find_library('GL'))
        signatures={
            'glEnable':([ctypes.c_uint],None),'glDisable':([ctypes.c_uint],None),
            'glClearColor':([ctypes.c_float]*4,None),'glClear':([ctypes.c_uint],None),
            'glViewport':([ctypes.c_int]*4,None),'glMatrixMode':([ctypes.c_uint],None),
            'glLoadIdentity':([],None),'glOrtho':([ctypes.c_double]*6,None),
            'glBegin':([ctypes.c_uint],None),'glEnd':([],None),
            'glVertex3f':([ctypes.c_float]*3,None),'glTexCoord2f':([ctypes.c_float]*2,None),
            'glColor4f':([ctypes.c_float]*4,None),'glBindTexture':([ctypes.c_uint]*2,None),
            'glGenTextures':([ctypes.c_int,ctypes.POINTER(ctypes.c_uint)],None),
            'glDeleteTextures':([ctypes.c_int,ctypes.POINTER(ctypes.c_uint)],None),
            'glTexParameteri':([ctypes.c_uint,ctypes.c_uint,ctypes.c_int],None),
            'glTexImage2D':([ctypes.c_uint,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,
                             ctypes.c_int,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p],None),
            'glBlendFunc':([ctypes.c_uint]*2,None),
            'glDepthMask':([ctypes.c_ubyte],None),
            'glColorMask':([ctypes.c_ubyte]*4,None),
            'glCullFace':([ctypes.c_uint],None),
            'glAlphaFunc':([ctypes.c_uint,ctypes.c_float],None),
            'glGetString':([ctypes.c_uint],ctypes.c_char_p)}
        for name,(args,result) in signatures.items():
            fn=getattr(library,name);fn.argtypes=args;fn.restype=result
        self.gl=library
        self.version=(library.glGetString(0x1f02) or b'').decode(errors='replace')
        self.context().aboutToBeDestroyed.connect(self.release)

    def release(self):
        if not self.gl:return
        self.makeCurrent()
        for identifier in (*self.ids.values(),*(i for layers in self.layer_ids.values() for i in layers)):
            value=ctypes.c_uint(identifier);self.gl.glDeleteTextures(1,ctypes.byref(value))
        self.ids={};self.layer_ids={};self.source=None
        if self.fragment_program:
            self.fragment_program.removeAllShaders();self.fragment_program.deleteLater();self.fragment_program=None
        self.fragment_failed=False;self.doneCurrent()

    def fragment_shader(self):
        if self.fragment_program:return True
        if self.fragment_failed:return False
        from PySide6.QtOpenGL import QOpenGLShader,QOpenGLShaderProgram
        from material_fragment import VERTEX_SHADER,FRAGMENT_SHADER
        program=QOpenGLShaderProgram(self)
        compiled=(program.addShaderFromSourceCode(QOpenGLShader.Vertex,VERTEX_SHADER)
                  and program.addShaderFromSourceCode(QOpenGLShader.Fragment,FRAGMENT_SHADER))
        if compiled:
            program.bindAttributeLocation('secondUV',1)
            program.bindAttributeLocation('maskUV',2)
            compiled=program.link()
        if not compiled:
            self.fragment_failed=True
            self.owner.graphicsUnavailable.emit('GPU Combiner shader недоступен: показан только Material1; '+program.log())
            program.removeAllShaders();program.deleteLater();return False
        self.fragment_program=program
        return True

    def upload(self):
        if self.source is self.owner.textures:return
        gl=self.gl
        for identifier in (*self.ids.values(),*(i for layers in self.layer_ids.values() for i in layers)):
            value=ctypes.c_uint(identifier);gl.glDeleteTextures(1,ctypes.byref(value))
        self.ids={};self.layer_ids={};self.source=self.owner.textures
        for slot,image in self.source.items():
            identifier=ctypes.c_uint();gl.glGenTextures(1,ctypes.byref(identifier))
            self.ids[slot]=identifier.value;gl.glBindTexture(0x0de1,identifier.value)
            wrap=self.owner.texture_wrap.get(slot,(0,0))
            for key,value in ((0x2801,0x2601),(0x2800,0x2601),
                              (0x2802,0x812f if wrap[0] else 0x2901),
                              (0x2803,0x812f if wrap[1] else 0x2901)):
                gl.glTexParameteri(0x0de1,key,value)
            data=ctypes.create_string_buffer(bytes(image.constBits()))
            gl.glTexImage2D(0x0de1,0,0x1908,image.width(),image.height(),0,0x1908,0x1401,data)
        surfaces=(self.owner.material_base or {}).get('textures',{})
        for slot,surface in surfaces.items():
            if not surface.get('fragment_layers') or not self.fragment_shader():continue
            self.layer_ids[slot]=[]
            for layer in surface['fragment_layers']:
                identifier=ctypes.c_uint();gl.glGenTextures(1,ctypes.byref(identifier))
                self.layer_ids[slot].append(identifier.value);gl.glBindTexture(0x0de1,identifier.value)
                wrap=layer['wrap']
                for key,value in ((0x2801,0x2601),(0x2800,0x2601),
                                  (0x2802,0x812f if wrap[0] else 0x2901),
                                  (0x2803,0x812f if wrap[1] else 0x2901)):
                    gl.glTexParameteri(0x0de1,key,value)
                data=ctypes.create_string_buffer(layer['pixels'])
                gl.glTexImage2D(0x0de1,0,0x1908,layer['width'],layer['height'],0,0x1908,0x1401,data)

    def paintGL(self):
        if not self.gl:return
        gl=self.gl;ratio=self.devicePixelRatioF()
        gl.glViewport(0,0,round(self.width()*ratio),round(self.height()*ratio))
        gl.glDepthMask(1)
        gl.glColorMask(1,1,1,1)
        gl.glClearColor(.094,.129,.161,1);gl.glClear(0x4000|0x0100)
        geometry=self.owner.geometry
        if not geometry:return
        fragment_faces=geometry.get('fragment_uv')
        vertex_colors=geometry.get('vertex_colors')
        # The widget has an opaque background. Keep its framebuffer alpha at one
        # while using texture alpha in blend factors; Qt composites/readbacks
        # interpret the framebuffer as premultiplied.
        gl.glColorMask(1,1,1,0)
        self.upload()
        points=project(geometry['points'],self.owner.yaw,self.owner.pitch)
        scale=min(self.width(),self.height())*.28*self.owner.zoom
        if not points or scale<=0:
            gl.glColorMask(1,1,1,1);return
        extent=max(2.,max(abs(p[2]) for p in points)+1)
        gl.glMatrixMode(0x1701);gl.glLoadIdentity()
        gl.glOrtho(-self.width()/scale/2,self.width()/scale/2,
                   -self.height()/scale/2,self.height()/scale/2,-extent,extent)
        gl.glMatrixMode(0x1700);gl.glLoadIdentity()
        gl.glEnable(0x0b71);gl.glEnable(0x0be2);gl.glBlendFunc(0x0302,0x0303)
        gl.glEnable(0x0bc0);gl.glAlphaFunc(0x0204,.05)
        px,py=self.owner.pan.x()/scale,-self.owner.pan.y()/scale
        # Back-to-front order also helps blended surfaces; opaque fragments
        # additionally use hardware depth testing.
        ordered=render_order(geometry,points,self.owner.material_states)
        missing_fragment_reported=False
        for index,face in ordered:
            texture=None
            if 'uv' in geometry and self.owner.style==2:
                texture=self.ids.get(geometry['face_materials'][index])
            state=self.owner.material_states.get(geometry['face_materials'][index],{}) if texture else {}
            blend=state.get('blend','alpha')
            (gl.glDisable if blend=='overwrite' else gl.glEnable)(0x0be2)
            gl.glBlendFunc(*BLENDS[blend])
            (gl.glEnable if state.get('alpha_test',True) else gl.glDisable)(0x0bc0)
            gl.glAlphaFunc(0x0204,state.get('alpha_ref',12.75)/255)
            (gl.glEnable if state.get('z_test',True) else gl.glDisable)(0x0b71)
            gl.glDepthMask(int(state.get('z_write',True)))
            (gl.glDisable if state.get('two_sided',True) else gl.glEnable)(0x0b44)
            gl.glCullFace(0x0405)
            if texture:
                gl.glEnable(0x0de1);gl.glBindTexture(0x0de1,texture);gl.glColor4f(1,1,1,1)
            else:gl.glDisable(0x0de1);gl.glColor4f(.51,.61,.66,1)
            slot=geometry['face_materials'][index] if texture else None
            layers=self.layer_ids.get(slot)
            surface=self.owner.material_base['textures'][slot] if layers else {}
            layer_uv=(fragment_faces[index] if surface.get('fragment_independent_uv')
                      and fragment_faces is not None and index<len(fragment_faces) else None)
            if layers and surface.get('fragment_independent_uv') and layer_uv is None:
                layers=None
                if not missing_fragment_reported:
                    self.owner.graphicsUnavailable.emit(
                        'GPU Combiner: независимые UV отсутствуют; показан только Material1')
                    missing_fragment_reported=True
            if layers:
                functions=self.context().functions()
                for unit,identifier in enumerate(layers):
                    functions.glActiveTexture(0x84c0+unit);gl.glBindTexture(0x0de1,identifier)
                functions.glActiveTexture(0x84c0)
                program=self.fragment_program;program.bind()
                for unit,name in enumerate(('firstMap','secondMap','maskMap')):program.setUniformValue1i(name,unit)
                program.setUniformValue1i('operation',surface['fragment_operation'])
                program.setUniformValue1i('alphaOperation',surface['fragment_alpha'])
                program.setUniformValue1i('invertMask',int(surface['fragment_invert']))
                program.setUniformValue1f('multiplier',float(surface.get('fragment_multiplier',1)))
            gl.glBegin(0x0004)
            for j in range(1,len(face)-1):
                for corner in (0,j,j+1):
                    if texture:
                        if vertex_colors is not None and vertex_colors[index] is not None:
                            gl.glColor4f(*(value/255. for value in vertex_colors[index][corner]))
                        uv=geometry['uv'][index][corner]
                        if layers:
                            functions.glVertexAttrib2f(1,*(layer_uv[1][corner] if layer_uv else uv))
                            functions.glVertexAttrib2f(2,*(layer_uv[2][corner] if layer_uv else uv))
                        gl.glTexCoord2f(*uv)
                    x,y,z=points[face[corner]];gl.glVertex3f(x+px,y+py,z)
            gl.glEnd()
            if layers:
                self.fragment_program.release()
                for unit in (1,2):
                    functions.glActiveTexture(0x84c0+unit);gl.glBindTexture(0x0de1,0)
                functions.glActiveTexture(0x84c0)
        gl.glDisable(0x0de1)
        gl.glDepthMask(1);gl.glDisable(0x0b44)
        gl.glColorMask(1,1,1,1)
