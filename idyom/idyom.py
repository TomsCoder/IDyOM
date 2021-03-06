from idyom import data
from idyom import markovChain
from idyom import longTermModel
from idyom import score
from idyom import jumpModel

import numpy as np
from glob import glob
import pickle
import matplotlib.pyplot as plt
import sys
from tqdm import tqdm

class idyom():
	"""
	This module represent the entire model, this is what you want to interact with if you only want to use the model.

	:param maxOrder: maximal order of the model
	:param viewPoints: viewPoint to use, cf. data.getViewPoints()

	:type maxOrder: int
	:type viewPoints: list of strings
	"""
	def __init__(self, maxOrder=None, viewPoints=["pitch", "length"], dataTrain=None, dataTrial=None, jump=False, maxDepth=10, stm=True):

		# viewpoints to use for the model
		self.viewPoints = viewPoints

		# maximal order for the markov chains
		self.maxOrder = maxOrder

		#maximal depth for the jump model
		self.maxDepth = maxDepth

		# we store wether we use jump
		self.jump = jump

		# wether we also use short term model or not
		self.stm = stm

		# list of all models for each viewpoints
		self.LTM = []
		for viewPoint in self.viewPoints:
			if self.jump is False:
				self.LTM.append(longTermModel.longTermModel(viewPoint, maxOrder=self.maxOrder))
			else:
				self.LTM.append(jumpModel.jumpModel(viewPoint, maxOrder=self.maxOrder, maxDepth=self.maxDepth))

	def train(self, data):
		"""
		Train the models from data
		
		:param data: data to train from

		:type data: data object
		"""

		k = 0
		for viewPoint in self.viewPoints:
			self.LTM[k].train(data.getData(viewPoint))
			k += 1

	def eval(self, data, k_fold=1):

		Likelihood = []

		for i in range(len(data.getData(self.viewPoints[0]))//k_fold):	

			# We initialize the models
			self.LTM = []
			for viewPoint in self.viewPoints:
				if self.jump is False:
					self.LTM.append(longTermModel.longTermModel(viewPoint, maxOrder=self.maxOrder))
				else:
					self.LTM.append(jumpModel.jumpModel(viewPoint, maxOrder=self.maxOrder, maxDepth=self.maxDepth))

			# We train them with the given dataset
			k = 0
			for viewPoint in self.viewPoints:
				self.LTM[k].train(data.getData(viewPoint)[:i*k_fold] + data.getData(viewPoint)[(i+1)*k_fold:])
				print(data.getData(viewPoint))
				print()
				print(data.getData(viewPoint)[:i*k_fold] + data.getData(viewPoint)[(i+1)*k_fold:])
				quit()
				k += 1

			#Likelihood.extend(self.getLikelihoodfromData(data))

	def mergeProbas(self, probas, weights, b=1):
		"""
		Merging probabilities from different models, for now we use arithmetic mean

		:param probas: probabilities to merge
		:param weights: weights for the mean, should be get from normalized entropy

		:type probas: list or numpy array
		:type weights: list or numpy array

		:return: merged probabilities (float)
		"""
		weights = np.array(weights) + 0.01
		# we inverse the entropies
		weights = (weights.astype(float)+np.finfo(float).eps)**(-b)
		
		# Doomy normalization
		for w in weights:
			if w < 0:
				weights = np.array(weights)
				weights += abs(min(weights))
				break
		if np.sum(weights) == 0:
			weights = np.ones(len(weights))

		weights = weights/np.sum(weights)

		ret = 0
		for i in range(len(probas)):
			ret += probas[i]*weights[i]

		return ret

	def getLikelihoodfromFile(self, file):
		"""
		Return likelihood over a score
		
		:param folder: file to compute likelihood on 

		:type data: string

		:return: np.array(length)

		"""

		D = data.data()
		D.addFile(file)

		probas = np.ones(D.getSizeofPiece(0))
		if self.jump is False:
			probas[0] = 1/len(self.LTM[0].models[0].alphabet)
		else:
			probas[0] = 1/len(self.LTM[0].models[0][0].alphabet)

		for model in self.LTM:
	
			dat = D.getData(model.viewPoint)[0]
			
			if self.jump is False:
				STM = longTermModel.longTermModel(model.viewPoint, maxOrder=20, STM=True, init=dat)
			else:
				STM = jumpModel.jumpModel(model.viewPoint, maxOrder=20)

			for i in tqdm(range(1, len(dat))):
				# we instanciate a Short Term Model for the current viewpoint

				if self.jump is True:
					STM = jumpModel.jumpModel(model.viewPoint, maxOrder=20)
					STM.train([dat[:i]])
				else:	
					STM.train([dat[:i]], shortTerm=True)

				p = model.getLikelihood(dat[:i], dat[i])

				flag = True

				# This happens when the state never happened in the training data
				if p is None:
					p = 0
					flag = None

				p2 = STM.getLikelihood(dat[:i], dat[i])

				if self.stm and p2 is not None:

					if flag is not None:
						p = self.mergeProbas([p, p2], [model.getEntropy(dat[:i]), STM.getEntropy(dat[:i])])
					else:
						p = p2
						
				probas[i] *= p

				if probas[i] == 563540:
					print("LTM:", model.getLikelihood(dat[:i], dat[i]))
					print("STM:", p2)
					#print("ret:", self.mergeProbas([p, p2], [model.getEntropy(dat[:i]), STM.getEntropy(dat[:i])]))
					print()

		return probas

	def getSurprisefromFile(self, file, zero_padding=False, time_representation=False):
		"""
		Return surprise(-log2(p)) over a score
		
		:param folder: file to compute surprise on 
		:param zero_padding: return surprise as spikes if True

		:type data: string
		:type zero_padding: bool

		:return: list of float

		"""

		D = data.data()
		D.addFile(file)

		probas = self.getLikelihoodfromFile(file)

		# We compute the surprise by using -log2(probas)
		probas = -np.log(probas+sys.float_info.epsilon)/np.log(2)

		if time_representation is False:
			return probas

		# We get the length of the notes
		lengths = D.getData("length")[0]

		ret = []
		for i in range(len(probas)):
			ret.append(probas[i])
			for j in range(int(lengths[i])):
				if zero_padding:
					ret.append(0)
				else:
					ret.append(probas[i])

		return ret

	def getLikelihoodfromData(self, D):

		ret = []

		for d in range(D.getSize()):
			probas = np.ones(D.getSizeofPiece(d))
			if self.jump is False:
				probas[0] = 1/len(self.LTM[0].models[0].alphabet)
			else:
				probas[0] = 1/len(self.LTM[0].models[0][0].alphabet)

				
			for model in self.LTM:
				dat = D.getData(model.viewPoint)[d]
				for i in range(1, len(dat)):
					p = model.getLikelihood(dat[:i], dat[i])
					probas[i] *= p

			ret.append(probas)

		return ret

	def getLikelihoodfromFolder(self, folder):
		"""
		Return likelihood over a all dataset
		
		:param folder: folder to compute likelihood on 

		:type data: string

		:return: a list of np.array(length)
		"""
		ret = []
		files = []
		for filename in tqdm(glob(folder + '/**', recursive=True)):
			if filename[filename.rfind("."):] in [".mid", ".midi"]:
				ret.append(self.getLikelihoodfromFile(filename))
				files.append(filename)

		return ret, files

	def getSurprisefromFolder(self, folder, zero_padding=True):
		"""
		Return likelihood over a all dataset
		
		:param folder: folder to compute likelihood on 
		:param zero_padding: return surprise as spikes if True

		:type data: string
		:type zero_padding: bool

		:return: a list of np.array(length)
		"""
		ret = []
		files = []
		for filename in tqdm(glob(folder + '/**', recursive=True)):
			if filename[filename.rfind("."):] in [".mid", ".midi"]:
				ret.append(self.getSurprisefromFile(filename, zero_padding=zero_padding))
				files.append(filename)

		return ret, files

	def sample(self, sequence):
		"""
		Sample the distribution from a given sequence, works only with pitch and length

		:param sequence: sequence of viewpoint data

		:type sequence: list

		:return: sample (int)
		"""

		probas = {}

		sequences = {}

		for model in self.LTM:
			sequences[model.viewPoint] = []

		for elem in sequence:
			for model in self.LTM:
				sequences[model.viewPoint].append(elem[model.viewPoint])

		for model in self.LTM:
			probas[model.viewPoint] = model.getPrediction(sequences[model.viewPoint])

		p = []
		notes = []
		for state1 in probas["pitch"]:
			for state2 in probas["length"]:
				if probas["pitch"][state1] is not None and probas["length"][state2] is not None:
					p.append(probas["pitch"][state1]*probas["length"][state2])
					tmp = {}
					tmp["pitch"] = int(state1)
					tmp["length"] = int(state2)
					notes.append(tmp)

		if np.sum(p) == 0:
			return None

		if np.sum(p) != 1:
			print(np.sum(p))
			p = p/np.sum(p)

		ret = np.random.choice(notes, p=p)

		return ret

	def generate(self, length):
		"""
		Return a piece of music generated using the model; works only with pitch and length.

		:param length: length of the output

		:type length: int

		:return: class piece
		"""

		S = [{"pitch": 74, "length": 24}]

		while len(S) < length and S[-1] is not None:
			S.append(self.sample(S))

		if S[-1] is None:
			S = S[:-1]

		ret = []
		for note in S:
			ret.extend([note["pitch"]]*note["length"])


		return score.score(ret)

	def benchmarkQuantization(self, folder, quantizations=[1,2,3,4,5,6,7,8,10,12,16,24,32,64], train=0.8):

		# We get all the midi files
		files = []
		for filename in glob(folder + '/**', recursive=True):
			if filename[filename.rfind("."):] in [".mid", ".midi"]:
				files.append(filename)

		np.random.shuffle(files)

		print("____ PROCESSING THE DATA")

		retMeans = np.zeros(len(quantizations))
		retStd = np.zeros(len(quantizations))
		k = 0
		for quantization in quantizations:

			trainData = data.data(quantization=quantization)
			trainData.addFiles(files[:int(train*len(files))])

			testData = data.data(quantization=quantization)
			testData.addFiles(files[int(train*len(files)):], augmentation=False)

			print(trainData.getData("length")[0])

			self.cleanWeights(order=self.maxOrder)
			self.train(trainData)
			
			tmp = self.getLikelihoodfromData(testData)
			means = np.zeros(testData.getSize())

			for i in range(len(tmp)):
				means[i] = np.mean(tmp[i])

			retMeans[k] = np.mean(means)
			retStd[k] = np.std(means)
			k += 1
		
		plt.plot(retMeans)
		plt.xticks(np.arange(len(retMeans)), quantizations)
		plt.ylabel('Likelihood over dataset')
		plt.xlabel('Quantization')
		plt.fill_between(range(len(retMeans)), retMeans + retStd, retMeans - retStd, alpha=.5)
		plt.show()

		return (retMeans, retStd)

	def benchmarkOrder(self, folder, maxOrder, train=0.8, saveFig=False):

		np.random.seed(0)
		# We get all the midi files
		files = []
		for filename in glob(folder + '/**', recursive=True):
			if filename[filename.rfind("."):] in [".mid", ".midi"]:
				files.append(filename)

		np.random.shuffle(files)

		print("____ PROCESSING THE DATA")

		trainData = data.data()
		trainData.addFiles(files[:int(train*len(files))], augmentation=True)

		testData = data.data()
		testData.addFiles(files[int(train*len(files)):], augmentation=False)

		retMeans = np.zeros(maxOrder)
		retStd = np.zeros(maxOrder)

		print("There is", trainData.getSize(),"scores for training")

		for order in range(1, maxOrder):
			self.cleanWeights(order=order)
			self.train(trainData)
			
			tmp = self.getLikelihoodfromData(testData)
			means = np.zeros(testData.getSize())

			for i in range(len(tmp)):
				means[i] = np.mean(tmp[i])

			retMeans[order] = np.mean(means)
			retStd[order] = np.std(means)
		
		plt.plot(retMeans)
		plt.ylabel('Likelihood over dataset')
		plt.xlabel('Max order of the model')
		plt.fill_between(range(len(retMeans)), retMeans + retStd, retMeans - retStd, alpha=.5)
		if saveFig is False:
			plt.show()
		else:
			plt.savefig("Benchmark_jump:"+str(self.jump)+".eps")

		print("TRAIN DATA")
		print(files[:int(train*len(files))])

		for i in range(len(means)):
			print(files[int(train*len(files)):][i],"->",means[i])

		return (retMeans, retStd)


	def cleanWeights(self, order=None):
		"""
		Delete all trained models and fix an order if given
		"""

		if order is None:
			order = self.maxOrder

		self.LTM = []
		for viewPoint in self.viewPoints:
			if self.jump is False:
				self.LTM.append(longTermModel.longTermModel(viewPoint, maxOrder=self.maxOrder))
			else:
				self.LTM.append(jumpModel.jumpModel(viewPoint, maxOrder=self.maxOrder, maxDepth=self.maxDepth))


	def save(self, file):
		"""
		Save a trained model
		
		:param file: path to the file
		:type file: string
		"""

		f = open(file, 'wb')
		pickle.dump(self.__dict__, f, 2)
		f.close()

	def load(self, path):
		"""
		Load a trained model

		:param path: path to the file
		:type path: string
		"""

		f = open(path, 'rb')
		tmp_dict = pickle.load(f)
		f.close()          

		self.__dict__.update(tmp_dict) 
