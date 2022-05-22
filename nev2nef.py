import sys
import os
import struct
import traceback
import subprocess
from PySide2.QtWidgets import *
from PySide2.QtCore import *
from PySide2.QtGui import *

app_name = "nev2nef"
app_ver = "0.2"
ffmpeg_path_default = "ffmpeg"
filename_suffix_digits_default = 6

NEFtemplate = "DSC_0557.NEF"
NEF_data_ptr = 0x256C00
#NEF_res_x_ptr = [0x892E, 0x8932, 0x2898E]
#NEF_res_y_ptr = [0x8930, 0x8934, 0x2899A, 0x289E2]
NEF_res_x_ptr = [0x8932, 0x2898E]
NEF_res_y_ptr = [0x8934, 0x2899A, 0x289E2]
NEF_offset_x_ptr = [0x8A34]
NEF_offset_y_ptr = [0x8A36]
NEF_res_x_valid_ptr = [0x8A38, 0x184DE]
NEF_res_y_valid_ptr = [0x8A3A, 0x184E0]
NEF_data_size_ptr = 0x289EE

margin_x = 12
margin_y = 8

mp4_boxtype_containers = ('moov', 'trak', 'edts', 'mdia', 'minf', 'dinf', 'stbl')

script_path = os.path.dirname(os.path.realpath(__file__))

class ProgressCanceled(Exception):
	pass

class NEVParser:
	def parse_mp4_boxes(self, f, datasize, indent):
		readsize = 0
		while readsize < datasize:
			header = f.read(8)
			if len(header) < 8:
				raise
			readsize += 8
			if indent == 0:
				if self.progbar.wasCanceled():
					raise ProgressCanceled
				self.progbar.setValue(readsize * 1000 // datasize)
				QApplication.processEvents()
			
			box_len, box_type = struct.unpack(">I4s", header)
			if box_len == 1:
				header_largesize = f.read(8)
				if len(header_largesize) < 8:
					raise
				readsize += 8
				box_len = struct.unpack(">Q", header_largesize)[0]
			
			box_type = box_type.decode("utf-8")
			#print(" "*indent, end="")
			#print(box_type, box_len)
			
			if box_type in mp4_boxtype_containers:
				self.parse_mp4_boxes(f, box_len - 8, indent+1)
			elif box_type == "stsc":
				# Sample-to-Chunk Atoms
				buf = f.read(box_len - 8)
				
				version   = buf[0]
				flags = buf[1:4]
				n_entries = struct.unpack('>I', buf[4:8])[0]
				
				for i in range(n_entries):
					i0 = 8 + i*12
					i1 = i0 + 12
					if len(buf) < i1: break
					first_chunk = struct.unpack('>I', buf[i0:i0+4])[0]
					samples_per_chunk = struct.unpack('>I', buf[i0+4:i0+8])[0]
					sample_desc_id = struct.unpack('>I', buf[i0+8:i0+12])[0]
					self.sc_table.append((first_chunk, samples_per_chunk, sample_desc_id))
					# print(f'{i:6d}: {(first_chunk, samples_per_chunk, sample_desc_id)}')
			elif box_type == "stsz":
				#Sample Size Atoms
				buf = f.read(box_len - 8)
				
				version   = buf[0]
				flags = buf[1:4]
				sample_size = struct.unpack('>I', buf[4:8])[0]
				n_entries = struct.unpack('>I', buf[8:12])[0]
				
				for i in range(n_entries):
					i0 = 12 + i*4
					i1 = i0 + 4
					if len(buf) < i1: break
					size = struct.unpack('>I', buf[i0:i1])[0]
					self.sz_table.append(size)
					# print(f'{i:6d}: {size}')
			elif box_type == "stco":
				#Chunk Offset Atoms
				buf = f.read(box_len - 8)
				
				version = buf[0]
				flags = buf[1:4]
				n_entries = struct.unpack('>I', buf[4:8])[0]
				
				for i in range(n_entries):
					i0 = 8 + i*4
					i1 = i0 + 4
					if len(buf) < i1: break
					offset = struct.unpack('>I', buf[i0:i1])[0]
					self.co_table.append(offset)
					# print(f'{i:6d}: {offset}')
			elif box_type == "co64":
				#64-bit chunk offset atoms
				buf = f.read(box_len - 8)

				version = buf[0]
				flags = buf[1:4]
				n_entries = struct.unpack('>I', buf[4:8])[0]

				for i in range(n_entries):
					i0 = 8 + i*8
					i1 = i0 + 8
					if len(buf) < i1: break
					offset = struct.unpack('>Q', buf[i0:i1])[0]
					self.co_table.append(offset)
					# print(f'{i:6d}: {offset}')
			else:
				f.seek(box_len - 8, 1)
			
			readsize += box_len - 8

	def parse_nraw_record(self, f, datalen):
		readlen = 0
		while readlen < datalen:
			header = f.read(8)
			box_len, box_type = struct.unpack(">I4s", header)
			#print(" ", box_type, box_len)
			
			bin = f.read(box_len - 8)
			#print(bin)
			#f.seek(box_len - 8, 1)
			readlen += box_len

	def parse_nraw(self, f, offset):
		f.seek(offset, 0)
		header = f.read(8)
		
		nraw_len, nraw_type = struct.unpack(">I4s", header)
		if nraw_type != b'NRAW':
			return
		#print(nraw_type, nraw_len)
		
		while True:
			header = f.read(8)
			box_len, box_type = struct.unpack(">I4s", header)
			
			if box_len == 0xFF10FF50:
				nraw_data_pos = f.tell() - 8
				nraw_data_size = nraw_len - nraw_data_pos + offset
				self.nraw_frames.append((nraw_data_pos, nraw_data_size))
				break
			
			#print(box_len, box_type)
			if box_type == b"NRFH" or box_type == b"NRTH":
				#self.parse_nraw_record(f, box_len - 8)
				f.seek(box_len - 8, 1)
			else:
				f.seek(box_len - 8, 1)
	
	def __init__(self, nev_path, progbar):
		self.sc_table = []
		self.sz_table = []
		self.co_table = []
		self.nraw_frames = []
		self.progbar = progbar
		
		f = open(nev_path, "rb")
		f.seek(0, 2)
		filesize = f.tell()
		f.seek(0, 0)
		self.parse_mp4_boxes(f, filesize, 0)
		
		self.progbar.setLabelText("Parsing NRAW structure")
		self.progbar.setRange(0, len(self.co_table))
		progval = 0
		for co in self.co_table:
			if self.progbar.wasCanceled():
				raise ProgressCanceled
			self.parse_nraw(f, co)
			progval += 1
			self.progbar.setValue(progval)
			QApplication.processEvents()

class Nev2NefDialog(QDialog):
	def __init__(self, parent=None):
		super(Nev2NefDialog, self).__init__(parent)
		
		self.setWindowTitle(app_name + " ver" + app_ver)
		self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
		
		layout = QVBoxLayout()
		
		hlayout1 = QHBoxLayout()
		self.nev_file_path = QLineEdit()
		self.nev_file_select_btn = QPushButton("...")
		self.nev_file_select_btn.setMinimumWidth(50)
		self.nev_file_select_btn.clicked.connect(self.nev_file_select)
		hlayout1.addWidget(QLabel("NEV file:"))
		hlayout1.addWidget(self.nev_file_path)
		hlayout1.addWidget(self.nev_file_select_btn)
		layout.addLayout(hlayout1)
		
		hlayout2 = QHBoxLayout()
		self.output_dir = QLineEdit()
		self.output_dir_select_btn = QPushButton("...")
		self.output_dir_select_btn.setMinimumWidth(50)
		self.output_dir_select_btn.clicked.connect(self.output_dir_select)
		hlayout2.addWidget(QLabel("Output directory:"))
		hlayout2.addWidget(self.output_dir)
		hlayout2.addWidget(self.output_dir_select_btn)
		layout.addLayout(hlayout2)
		
		hlayout3 = QHBoxLayout()
		self.filename_prefix = QLineEdit()
		self.filename_suffix_digits = QSpinBox()
		self.filename_suffix_digits.setRange(1, 32)
		self.filename_suffix_digits.setValue(filename_suffix_digits_default)
		hlayout3.addWidget(QLabel("Filename prefix:"))
		hlayout3.addWidget(self.filename_prefix)
		hlayout3.addWidget(QLabel("  suffix digits:"))
		hlayout3.addWidget(self.filename_suffix_digits)
		layout.addLayout(hlayout3)
		
		hlayout4 = QHBoxLayout()
		self.output_wav_chk = QCheckBox()
		self.ffmpeg_path = QLineEdit()
		self.ffmpeg_path.setText(ffmpeg_path_default)
		hlayout4.addWidget(QLabel("Demux wav (need ffmpeg):"))
		hlayout4.addWidget(self.output_wav_chk)
		hlayout4.addWidget(QLabel("  ffmpeg path:"))
		hlayout4.addWidget(self.ffmpeg_path)
		layout.addLayout(hlayout4)
		
		vlayout5 = QVBoxLayout()
		hlayout5_1 = QHBoxLayout()
		hlayout5_2 = QHBoxLayout()
		self.fs_all = QRadioButton("All frames")
		self.fs_one = QRadioButton("One frame")
		self.fs_one.setChecked(True)
		self.fs_frame = QSpinBox()
		self.fs_frame.setRange(0, 9999999)
		self.fs_range = QRadioButton("Range")
		self.fs_frame_start = QSpinBox()
		self.fs_frame_start.setRange(0, 9999999)
		self.fs_frame_end = QSpinBox()
		self.fs_frame_start.setValue(100)
		self.fs_frame_end.setRange(0, 9999999)
		self.fs_frame_end.setValue(200)
		frame_select_group = QGroupBox("Frame selection")
		frame_select_group.setLayout(vlayout5)
		vlayout5.addWidget(self.fs_all)
		hlayout5_1.addWidget(self.fs_one)
		hlayout5_1.addWidget(self.fs_frame)
		hlayout5_1.addStretch()
		vlayout5.addLayout(hlayout5_1)
		hlayout5_2.addWidget(self.fs_range)
		hlayout5_2.addWidget(self.fs_frame_start)
		hlayout5_2.addWidget(QLabel(" to "))
		hlayout5_2.addWidget(self.fs_frame_end)
		hlayout5_2.addStretch()
		vlayout5.addLayout(hlayout5_2)
		layout.addWidget(frame_select_group)
		
		hlayout6 = QHBoxLayout()
		self.resolution = QComboBox()
		self.resolution.addItem("8.3K(8268x4652)")
		self.resolution.addItem("5.4K(5404x3040)")
		hlayout6.addWidget(QLabel("Resolution:"))
		hlayout6.addWidget(self.resolution)
		hlayout6.addStretch()
		layout.addLayout(hlayout6)
		
		self.start_convert_btn = QPushButton("Convert")
		self.start_convert_btn.clicked.connect(self.start_convert)
		layout.addWidget(self.start_convert_btn)
		
		self.setLayout(layout)
	
	def nev_file_select(self):
		nev_path = QFileDialog.getOpenFileName(self, "Open NEV file", os.getcwd(), "NEV Files (*.nev)")[0]
		if nev_path != "":
			self.nev_file_path.setText(nev_path)
			if self.output_dir.text() == "":
				self.output_dir.setText(os.path.splitext(nev_path)[0])
			nev_name = os.path.basename(os.path.splitext(nev_path)[0])
			self.filename_prefix.setText(nev_name + "_")
	
	def output_dir_select(self):
		outdir = QFileDialog.getExistingDirectory()
		if outdir != "":
			self.output_dir.setText(outdir)
	
	def output_frame(self, nef_header, resolution, f_nev, frame, nraw_frames):
		fname = self.filename_prefix.text() + str(frame).zfill(self.filename_suffix_digits.value()) + ".nef"
		out_path = os.path.join(self.output_dir.text(), fname)
		f_out = open(out_path, "wb")
		f_out.write(nef_header)
		
		for res_x_ptr in NEF_res_x_ptr:
			f_out.seek(res_x_ptr, 0)
			f_out.write(struct.pack("<H", resolution[0]))
		
		for res_y_ptr in NEF_res_y_ptr:
			f_out.seek(res_y_ptr, 0)
			f_out.write(struct.pack("<H", resolution[1]))
		
		for res_x_valid_ptr in NEF_res_x_valid_ptr:
			f_out.seek(res_x_valid_ptr, 0)
			f_out.write(struct.pack("<H", resolution[0] - margin_x))
		
		for res_y_valid_ptr in NEF_res_y_valid_ptr:
			f_out.seek(res_y_valid_ptr, 0)
			f_out.write(struct.pack("<H", resolution[1] - margin_y))
		
		for offset_x_ptr in NEF_offset_x_ptr:
			f_out.seek(offset_x_ptr, 0)
			f_out.write(struct.pack("<H", margin_x//2))
		
		for offset_y_ptr in NEF_offset_y_ptr:
			f_out.seek(offset_y_ptr, 0)
			f_out.write(struct.pack("<H", margin_y//2))
		
		f_out.seek(0, 2)
		
		f_nev.seek(nraw_frames[frame][0])
		frame_buf = f_nev.read(nraw_frames[frame][1])
		
		f_out.write(frame_buf)
		
		f_out.seek(NEF_data_size_ptr, 0)
		f_out.write(struct.pack("<I", nraw_frames[frame][1]))
		
		f_out.close()
	
	def start_convert(self):
		self.start_convert_btn.setEnabled(False)
		
		try:
			progbar = QProgressDialog("Parsing mp4 structure", "Cancel", 0, 1000, parent = self)
			progbar.setWindowModality(Qt.WindowModal)
			progbar.show()
			
			nev_path = self.nev_file_path.text()
			nraw_frames = NEVParser(nev_path, progbar).nraw_frames
			
			nef_template_path = os.path.join(script_path, NEFtemplate)
			f = open(nef_template_path, "rb")
			nef_header = f.read(NEF_data_ptr)
			f.close()
			
			if self.resolution.currentIndex() == 0:
				resolution = (8268, 4652)
			else:
				resolution = (5404, 3040)
			
			f_nev = open(self.nev_file_path.text(), "rb")
			
			if not os.path.exists(self.output_dir.text()):
				os.makedirs(self.output_dir.text())
			
			if self.fs_all.isChecked():
				fs = range(0, len(nraw_frames))
			elif self.fs_one.isChecked():
				fs = [self.fs_frame.value()]
			else:
				fs = range(self.fs_frame_start.value(), self.fs_frame_end.value()+1)
			
			progbar.setLabelText("Writing RAW files")
			progbar.setRange(0, len(fs))
			progval = 0
			for frame in fs:
				if progbar.wasCanceled():
					raise ProgressCanceled
				progval += 1
				self.output_frame(nef_header, resolution, f_nev, frame, nraw_frames)
				progbar.setValue(progval)
				QApplication.processEvents()
			
			f_nev.close()
			
			if self.output_wav_chk.isChecked():
				progbar.setLabelText("Writing Wav file")
				progbar.setRange(0, 0)
				wav_path = os.path.join(self.output_dir.text(), self.filename_prefix.text() + "audio.wav")
				cmd = [self.ffmpeg_path.text(), "-n", "-i", nev_path, "-vn", "-acodec", "copy", wav_path]
				subprocess.call(cmd)
		
		except ProgressCanceled:
			QMessageBox.critical(self, app_name, "Canceled")
		except:
			QMessageBox.critical(self, app_name, "An exception occurred while processing.\n\n" + traceback.format_exc())
		else:
			QMessageBox.information(self, app_name, "Done!")
		
		progbar.close()
		self.start_convert_btn.setEnabled(True)

app = QApplication(sys.argv)
dlg = Nev2NefDialog()
dlg.show()
app.exec_()