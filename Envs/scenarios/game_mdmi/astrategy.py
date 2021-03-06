import numpy as np
from pyllist import dllist
from math import pi, atan2
from ortools.linear_solver import pywraplp

from Envs.scenarios.game_mdmi.geometries import dist, norm, DominantRegion
		

def efficiency(xd, xi, target, r, a):
	dr = DominantRegion(r, a, xi, [xd], offset=0)
	xw = target.deepest_point_in_dr(dr)
	tlevel = target.level(xw)
	dlevel = dist(xw, xd)
	return tlevel/dlevel

class DAssignment(object):
	"""docstring for DAssignment"""
			
	def __init__(self, did, ub):
		self.id = did
		self.ub = ub
		self.reset()

	def sort_dict(self, dic):
		return {k:v for k, v in sorted(dic.items(), key=lambda x: x[1])}

	def add_ccap(self, iids, es=None):
		if not isinstance(iids, list): iids = [iids]
		if not isinstance(es, list): es = [es]

		for i, e in zip(iids, es):
			if e is not None:
				self.e.update({str(i): e})

		self.ccap = self.ccap.union(set(iids))

	def add_excl(self, iids, es=None):
		if not isinstance(iids, list): iids = [iids]
		if not isinstance(es, list): es = [es]

		for i, e in zip(iids, es):
			if e is not None:
				self.e.update({str(i): e})

		self.excl = self.excl.union(set(iids))		

	def add_assd(self, iids, es=None):
		if not isinstance(iids, list): iids = [iids]
		if not isinstance(es, list): es = [es]

		for i, e in zip(iids, es):
			if e is None:
				assert str(i) in self.e
				e = self.e[str(i)]
			else:
				self.e.update({str(i): e})
			if self.n >= self.ub:
				key, var = next(iter(self.assd.items()))
				if e > var: # if e is larger than the existing smallest in assigned intruders, replace in
					self.assd.pop(key)	
					self.assd.update({str(i): e})
					self.assd = self.sort_dict(self.assd)
			else:
				self.assd.update({str(i): e})
				self.assd = self.sort_dict(self.assd)
				self.n += 1

	def reset(self):
		self.ccap = set()
		self.excl = set()
		self.e = set()
		self.assd = dict()
		self.n = 0

class IAssignment(object):
	"""docstring for DAssignment"""
			
	def __init__(self, did):
		self.id = did
		self.reset()

	def add_ccap(self, did):
		if isinstance(did, int):
			self.ccap = self.ccap.union({did})
		elif isinstance(did, list):
			self.ccap = self.ccap.union(set(did))

	def add_assd(self, did):
		if isinstance(did, int):
			self.assd = self.assd.union({did})
			self.n += 1
		elif isinstance(did, list):
			self.assd = self.assd.union(set(did))
			self.n += len(did)

	def reset(self):
		self.ccap = set()
		self.assd = set()
		self.n = 0

def group_defenders(world, dset):
	# print('================ grouping defenders ===========')
	Rd = world.defenders[0].Rd
	groups = []
	for d in dset:
		# print('----------- for %d---------'%d)
		found = False
		for i, g in enumerate(groups):
			# print('>>>>> checking', g, 'from', groups)
			for din in g:
				d_din = dist(world.defenders[d].state.p_pos, 
						world.defenders[din].state.p_pos)
				# print('>> checking', din, 'from', g, 'distance: ', d_din, 'Rd', Rd)
				if d_din < Rd:
					found = True
					break;
			if found:
				# print('found 2!!!!!!!!')
				break;
		if found: # if d is connected to existing groups, add d to the group
			groups[i] = g.union({d})
			# print('add %d to the currend group'%d, groups)
		else: # otherwise create a new group for d
			groups.append({d})
			# print('add another group', groups)

	# print(groups, dset)
	return groups


def knapsack_assign(world, firstassign=False, sparse=False):
	# new assignment only when some intruder is captured
	if sparse:
		if firstassign: 
			rassign = True
		else:
			rassign = False
			for intruder in world.intruders:
				rassign = rassign or intruder.mem.e != intruder.state.e or intruder.mem.n != intruder.state.n
		if not rassign:
			return

	# declare
	lb = np.floor(world.ni/world.nd)
	ub = min(3, np.ceil(world.ni/world.nd)+0)
	Dassign = [DAssignment(d.id, ub) for d in world.defenders]
	Iassign = [IAssignment(i.id) for i in world.intruders]
	eff = [[None for j in world.defenders] for i in world.intruders]

	## intruders that can be captured
	for i, I in enumerate(world.intruders):
		for j, D in enumerate(world.defenders):
				if i in D.neigh_i and I.state.a:
					e = efficiency(D.state.p_pos, I.state.p_pos, world.target, world.r, D.max_speed/I.max_speed)
					# if e > -5.:
					Dassign[j].add_ccap(I.id, e)
					Iassign[i].add_ccap(D.id)
					eff[i][j] = e

	## intruders that can only be captured by one of the defenders		
	i_to_assign = []		
	i_to_assign = [i for i in range(world.ni)]

	## assign intruders among defenders that can capture them
	x = [[None for d in world.defenders] for i in world.intruders]
	solver = pywraplp.Solver('player_assign',
								pywraplp.Solver.CBC_MIXED_INTEGER_PROGRAMMING)
	obj_expr = []
	capaci_cons_expr = [[] for _ in world.defenders]
	for i in i_to_assign:
		groups = group_defenders(world, Iassign[i].ccap)
		# print(i, Iassign[i].ccap, groups)
		for g in groups:
			permit_cons_expr = [] # the intruder can only be assigned to 
								  # one defender in a connected group			
			for j in list(g):
			# for j in list(Iassign[i].ccap):
				if Dassign[j].ub > Dassign[j].n:
					x[i][j] = solver.IntVar(0, 1, 'x[%i,%i]'%(i, j))
					permit_cons_expr.append(x[i][j])
					capaci_cons_expr[j].append(x[i][j])
					obj_expr.append(x[i][j]*eff[i][j])
			solver.Add(solver.Sum(permit_cons_expr) <= 1)

	# capacity constraint
	for j, ccons in enumerate(capaci_cons_expr):
		if len(ccons) > 0:
			solver.Add(solver.Sum(ccons) <= (Dassign[j].ub - Dassign[j].n))

	solver.Maximize(solver.Sum(obj_expr))
	status = solver.Solve()

	for i, assigned_intruder in enumerate(x):
		for d, assignto_defender in enumerate(assigned_intruder):
			if assignto_defender is not None:
				if assignto_defender.solution_value() > 0:
					Dassign[d].add_assd(i, eff[i][d])
					Iassign[i].add_assd(d)
	et = 0.
	nassd = 0
	# print('------------knapsack_assign-------------')
	for d, (defender, Dass) in enumerate(zip(world.defenders, Dassign)):
		
		defender.state.o = [int(i) for i in Dass.assd]
		defender.state.f = [e for i, e in Dass.assd.items()]
		defender.state.s = 'opt'
		# print(defender.neigh_i, [ee[d] for ee in eff])
		# print(d, defender.state.o)
		for i in Dass.assd:
			et += eff[int(i)][d]
			nassd += 1
	# print(et)
	return nassd, et

def negotiate_assign(world, firstassign=False, sparse=False, aug=False):
	# new assignment only when some intruder is captured
	if sparse:
		if firstassign: 
			rassign = True
		else:
			rassign = False
			for intruder in world.intruders:
				rassign = rassign or intruder.mem.e != intruder.state.e or intruder.mem.n != intruder.state.n
		if not rassign:
			return

	# declare
	ub = min(3, int(np.ceil(world.ni/world.nd)))
	Dcand = [[] for d in range(world.nd)]
	Dpin = [None for d in range(world.nd)]
	Dassign = [[] for _ in range(world.nd)]
	es = [[None for _ in range(world.ni)] for _ in range(world.nd)]

	for d, D in enumerate(world.defenders):
		temp = []
		for i in D.neigh_i:
			e = efficiency(D.state.p_pos, world.intruders[i].state.p_pos, 
						   world.target, world.r, 
						   D.max_speed/world.intruders[i].max_speed)
			es[d][i] = e
			temp.append((i, e))

		Dcand[d] = dllist([i for i, e in sorted(temp, key=lambda x: x[1])])
		Dpin[d] = 0 if Dcand[d].size <= ub else -ub
		Dassign[d] = [n.value for n in Dcand[d].nodeat(Dpin[d]).iternext()] if Dcand[d].size > 0 else []

	def recusive(world=world, Dassign=Dassign, Dpin=Dpin, es=es, Dcand=Dcand, aug=aug):
		nconflict = 0
		for j, D in enumerate(world.defenders):
			nremoved = 0
			for n_i in Dassign[j][::-1]:
				for n_d in D.neigh_d: # if other defender can capture the intruder more effectively, remove
					if n_i in Dassign[n_d]:
						if es[n_d][n_i] is None:
							es[n_d][n_i] = efficiency(world.defenders[n_d].state.p_pos, 
											world.intruders[n_i].state.p_pos, 
											world.target, world.r, 
											world.defenders[n_d].max_speed/world.intruders[n_i].max_speed)
						if es[j][n_i] < es[n_d][n_i]:
							Dassign[j].remove(n_i)
							nremoved += 1
							break

			for k in range(nremoved):
				if Dcand[j].nodeat(Dpin[j]).prev is not None:
					Dassign[j] = [Dcand[j].nodeat(Dpin[j]).prev.value] + Dassign[j]
					Dpin[j] -= 1

			nconflict += nremoved
		return nconflict > 0

	conflict = True
	while conflict:
		conflict = recusive()	

	et = 0.
	nassd = 0
	# print('-----------negotiate_assign--------------')
	for d, (defender, assign) in enumerate(zip(world.defenders, Dassign)):
		# print(d, assign)
		defender.state.o = assign
		defender.state.f = [es[d][i] for i in assign]
		defender.state.s = 'pwn'
		# for k, e in zip(Dcand[d], es[d]):
			# print(k, e)
		# print('    '.join(['(%s, %.3f)'%(k, es[d][k]) for k in Dcand[d]][::-1]))
		for i in assign:
			et += es[d][i]
			nassd += 1
	# print(et)			
	# print('---------------------------------------------------')

	return nassd, et


def augmented_negotiation(world, firstassign=False, sparse=False, aug=False):
	# new assignment only when some intruder is captured
	if sparse:
		if firstassign: 
			rassign = True
		else:
			rassign = False
			for intruder in world.intruders:
				rassign = rassign or intruder.mem.e != intruder.state.e or intruder.mem.n != intruder.state.n
		if not rassign:
			return

	# declare
	ub = min(3, int(np.ceil(world.ni/world.nd)))
	Dcand = [[] for d in range(world.nd)]
	# Ncand = [None for d in range(world.nd)]
	Dpin = [None for d in range(world.nd)]
	# Dpin_ = [-1 for d in range(world.nd)]
	Dassign = [None for _ in range(world.nd)]
	Dhist = [dict() for _ in range(world.nd)] # for augmented PN
	es = [[None for _ in range(world.ni)] for _ in range(world.nd)]

	for d, D in enumerate(world.defenders):
		temp = []
		for i in D.neigh_i:
			e = efficiency(D.state.p_pos, world.intruders[i].state.p_pos, 
						   world.target, world.r, 
						   D.max_speed/world.intruders[i].max_speed)
			es[d][i] = e
			temp.append((i, e))

		# candidate list
		Dcand[d] = [i for i, e in sorted(temp, key=lambda x: x[1])]

		# Dpin: locations of preferred intruder in the candidate list
		n = len(Dcand[d])
		if n <= ub:
			Dpin[d] = [ipin for ipin in range(-n, 0)]
		else:
			Dpin[d] = [ipin for ipin in range(-ub, 0)]

		# confilict history
		Dhist[d] = {str(Dcand[d][ipin]): es[d][Dcand[d][ipin]] for ipin in Dpin[d]}
		# Dpin[d] = -Dcand[d].size if Dcand[d].size <= ub else -ub
		# Ncand[d] = n
		# Dhist[d] = {str(Dcand[d][ipin]):es[d][Dcand[d][ipin]] for ipin in range(Dpin[d], Dpin_[d]+1)}
		# print(Dhist[d], Dcand[d])
		# assn = [n.value for n in Dcand[d].nodeat(Dpin[d]).iternext()] if Dcand[d].size > 0 else []
		
		# Dassign[d] = dllist(assn)

	# record the length of the candidate list
	Ncand = [len(dcand) for dcand in Dcand]

	# def recusive(world=world, Dassign=Dassign, Dpin=Dpin, Dpin_=Dpin_, es=es, Dcand=Dcand, Dhist=Dhist):
	# 	nconflict = 0
	# 	for j, D in enumerate(world.defenders):
	# 		nremoved = 0
	# 		# negotiate about the preferred intruder list
	# 		for n_i in Dassign[j][::-1]:
	# 			emax = -np.inf # for augmented PN
	# 			iremoved = False # byproduct of adding augmented PN
	# 			for n_d in D.neigh_d: # if other defender can capture the intruder more effectively, remove
	# 				if n_i in Dassign[n_d]:
	# 					if es[n_d][n_i] is None:
	# 						es[n_d][n_i] = efficiency(world.defenders[n_d].state.p_pos, 
	# 										world.intruders[n_i].state.p_pos, 
	# 										world.target, world.r, 
	# 										world.defenders[n_d].max_speed/world.intruders[n_i].max_speed)
	# 					if es[j][n_i] < es[n_d][n_i]:
	# 						if not iremoved:
	# 							Dassign[j].remove(n_i)
	# 							iremoved = True # by product of adding augmented PN
	# 							nremoved += 1
	# 							Dpin_[j] -= 1
	# 						emax = max(emax, es[n_d][n_i]) # for augmented PN
	# 				if str(n_i) in Dhist[n_d]: # for augmented PN
	# 					if es[j][n_i] < Dhist[n_d][str(n_i)]:
	# 						if not iremoved:
	# 							Dassign[j].remove(n_i)
	# 							iremoved = True
	# 							nremoved += 1
	# 							Dpin_[j] -= 1
	# 						emax = max(emax, Dhist[n_d][str(n_i)])
	# 			if iremoved: # for augmented PN: record the highest efficiency encountered
	# 				Dhist[j].update({str(n_i):emax})
	# 		for k in range(nremoved):
	# 			if Dcand[j].nodeat(Dpin[j]).prev is not None:
	# 				Dassign[j] = [Dcand[j].nodeat(Dpin[j]).prev.value] + Dassign[j]
	# 				Dpin[j] -= 1
	# 		nconflict += nremoved

	# 		# continue to update the conflict history
	# 		n_i_ = Dpin_[j] + 1
	# 		while n_i_ < 0:
	# 			emax_ = Dhist[j][str(n_i_)] # current max: from own history
	# 			for n_d_ in D.neigh_d:
	# 				if str(n_i_) in Dhist[n_d_]: # for augmented PN
	# 					if es[j][n_i_] < Dhist[n_d_][str(n_i_)]:
	# 						emax_ = max(emax_, Dhist[n_d_][str(n_i_)])
	# 			Dhist[j].update({str(n_i_): emax_})
	# 			n_i_ += 1

	# 	return nconflict > 0

	def recusive(world=world, Dpin=Dpin, es=es, Dcand=Dcand, Dhist=Dhist):
		nconflict = 0
		for j, D in enumerate(world.defenders):
			# print('-----------------%d-----------------'%j, [Ncand[j][ii] for ii in Dpin[j]], Dcand[j], Dhist[j])
			# print('D%d: '%j, [Dcand[j][ii] for ii in Dpin[j]], Dcand[j], Dhist[j])
			nremoved = 0
			if Ncand[j]>0:
				ipin = -1
				ipin_min = Dpin[j][0] if Dpin[j] else -Ncand[j]
				while ipin >= ipin_min: # intruders (currently or used to be) in preferred list
					i = Dcand[j][ipin]
					found = False
					emax = Dhist[j][str(i)]
					nd_max = j
					for n_d in D.neigh_d:
						if str(i) in Dhist[n_d] and es[j][i] < Dhist[n_d][str(i)]:
							# emax = max(emax, Dhist[n_d][str(i)])
							if Dhist[n_d][str(i)] > emax:
								emax = Dhist[n_d][str(i)]
								nd_max = n_d
							found = True
							# print('-.-.-.-.-.-.-.found', n_d, 'has higher e for', i,  Dhist[n_d])
					if found:
						Dhist[j].update({str(i): emax}) # update conflict history
						if ipin in Dpin[j]:  # delete the intruder if its in the preferred list
							Dpin[j].pop(Dpin[j].index(ipin))
							nremoved += 1
						# print('------------- found e_%d_%d>e_%d_%d, remove %d'%(nd_max, i, j, i, i))
					ipin -= 1
			# add other intruders to the preferred list if exist
				for k in range(nremoved):
					if ipin_min <= -Ncand[j]:
						break
					ipin_min -= 1
					Dpin[j] = [ipin_min] + Dpin[j]
					newi = Dcand[j][ipin_min]
					Dhist[j].update({str(newi): es[j][newi]})

			nconflict += nremoved

		return nconflict > 0

	conflict = True
	# print('>>>>>>>>>start>>>>>>>>>>>>>>>>')
	while conflict:
		# print('===================')
		conflict = recusive()

	for d, (dpin, dcand) in enumerate(zip(Dpin, Dcand)):
		Dassign[d] = [dcand[ipin] for ipin in dpin]

	et = 0.
	nassd = 0
	# print('------------augmented_negotiation-------------')
	for d, (defender, assign) in enumerate(zip(world.defenders, Dassign)):
		# print(d, assign)
		defender.state.o = assign
		defender.state.f = [es[d][i] for i in assign]
		defender.state.s = 'pwn'
		# for k, e in zip(Dcand[d], es[d]):
			# print(k, e)
		# print('    '.join(['(%s, %.3f)'%(k, es[d][k]) for k in Dcand[d]][::-1]))
		for i in assign:
			et += es[d][i]
			nassd += 1
	# print(et)
	# print('---------------------------------------------------')

	return nassd, et



def extended_negotiation(world, firstassign=False, sparse=False):
	# new assignment only when some intruder is captured
	if sparse:
		if firstassign: 
			rassign = True
		else:
			rassign = False
			for intruder in world.intruders:
				rassign = rassign or intruder.mem.e != intruder.state.e or intruder.mem.n != intruder.state.n
		if not rassign:
			return

	# declare
	ub = int(np.ceil(world.ni/world.nd))
	Dcand = [None for d in range(world.nd)]
	Dw8tl = [[] for d in range(world.nd)]
	# Dcomp = [None for d in range(world.nd)]

	# Dpin = [None for d in range(world.nd)]
	Dassign = [[] for _ in range(world.nd)]
	es = [[None for _ in range(world.ni)] for _ in range(world.nd)]

	for d, D in enumerate(world.defenders):
		temp = []
		for i in D.neigh_i:
			e = efficiency(D.state.p_pos, world.intruders[i].state.p_pos, 
						   world.target, world.r, 
						   D.max_speed/world.intruders[i].max_speed)
			es[d][i] = e
			temp.append((i, e))

		temp_sorted = sorted(temp, key=lambda x: x[1], reverse=True)
		Dcand[d] = [i for i, e in temp_sorted]
		# Dcomp[d] = [i for i, e in temp_sorted]
		# Dpin[d] = 0 if Dcand[d].size <= ub else -ub
		# Dassign[d] = [n.value for n in Dcand[d].nodeat(Dpin[d]).iternext()] if Dcand[d].size > 0 else []

	nn = 0
	while not all([len(cand)==0 for cand in Dcand]):
		# print('--------------------- iter', nn, '--------------------------')
		for d, (D, cand) in enumerate(zip(world.defenders, Dcand)):
			for n_i in cand:
				for n_d in D.neigh_d: # if other defender can capture the intruder more effectively, remove
					if n_i in Dcand[n_d]:
						if es[n_d][n_i] is None:
							es[n_d][n_i] = efficiency(world.defenders[n_d].state.p_pos, 
											world.intruders[n_i].state.p_pos, 
											world.target, world.r, 
											world.defenders[n_d].max_speed/world.intruders[n_i].max_speed)
						if es[d][n_i] < es[n_d][n_i]:
							Dw8tl[d].append(n_i)
							break

		# for d, (cand, w8tl) in enumerate(zip(Dcand, Dw8tl)):
		# 	print('defender %d candidates: '%d, cand, w8tl)

		for d, (D, cand, w8tl) in enumerate(zip(world.defenders, Dcand, Dw8tl)):
			for i in cand:
				if i not in w8tl and len(Dassign[d]) < ub:
					Dassign[d].append(i)
			# if len(Dassign[d]) >= ub:
			# 	Dcand[d][0] = []


		# for d, ass in enumerate(Dassign):
		# 	print('defender %d assigns'%d, ass)

		# put unassigned intruders of the original candidate list into a new candidate list
		for d in range(world.nd):
			Dcand[d] = [i for i in Dcand[d] if i not in Dassign[d]] if len(Dassign[d]) < ub else []
			Dw8tl[d] = [] # reset waiting list

		# delete assigned intruders from the new candidate list
		for d, D in enumerate(world.defenders):
			for n_d in D.neigh_d:
				for n_i in Dassign[n_d]:
					if n_i in Dcand[d]:
						Dcand[d].remove(n_i)
		nn += 1


	et = 0.
	nassd = 0
	for d, (defender, assign) in enumerate(zip(world.defenders, Dassign)):
		defender.state.o = assign
		# for k, e in zip(Dcand[d], es[d]):
		# 	print(k, e)
		# print('    '.join(['(%s, %.3f)'%(k, es[d][k]) for k in Dcand[d]][::-1]))
		for i in assign:
			et += es[d][i]
			nassd += 1
	# print('---------------------------------------------------')

	return nassd, et					
