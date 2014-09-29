#!/usr/bin/python
# -*- coding: utf-8 -*-
#coding:utf-8

import os
import Tkinter as tk
from PIL import Image, ImageTk

class captchaDialog:
	def __init__(self,parent, imgPath):
		#self.root = tk.Toplevel(parent)
		self.root = parent
		self.imgPath = imgPath
		self.value=""
		self.initUI();

	def onInputChange(self,str_var):
		val=str_var.get()
		if len(val) >= 4:
			self.root.after(0, lambda: self.onExit()) #auto close window after captcha input finish
		return str_var.get()

	def initUI(self):
		captchaIpt = tk.StringVar()
		captchaIpt.trace("w", lambda name, index, mode, captcha=captchaIpt: self.onInputChange(captcha))

		#label
		# http://www.python-course.eu/tkinter_labels.php
		self.img = Image.open(self.imgPath)
		self.photo_image = ImageTk.PhotoImage(self.img) #must keep a reference here to prevent the gc
		label = tk.Label(self.root,image=self.photo_image)
		label.pack(side=tk.LEFT)

		# edit input
		self.e = tk.Entry(self.root, textvariable=captchaIpt)
		self.e.pack(side=tk.LEFT)
		self.e.focus_set()

	def onExit(self):
		self.value = self.e.get()
		self.root.destroy()

def show_captcha(captchaPath):
	root = tk.Tk()
	d = captchaDialog(root,captchaPath)

	# center window
	w = root.winfo_screenwidth()
	h = root.winfo_screenheight()
	rootsize = (240,80)
	x = w/2 - rootsize[0]/2
	y = h/2 - rootsize[1]/2
	root.title("")
	root.geometry("%dx%d+%d+%d" % (rootsize + (x, y)))

	#put window to topmost and grab the focus
	root.attributes("-topmost", 1)
	root.focus_force()

	#root.withdraw() # hide main window
	root.wait_window(d.root)
	return d.value

def main():
	a = show_captcha(os.path.join(os.getcwd(),"pass_code.jpeg"))
	print a

if __name__ == '__main__':
	main()
