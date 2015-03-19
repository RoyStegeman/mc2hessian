#!/usr/bin/env python
""" Find the best basis with a GA """

__author__ = 'Stefano Carrazza'
__license__ = 'GPL'
__version__ = '1.0.0'
__email__ = 'stefano.carrazza@mi.infn.it'

import sys
import argparse

import numpy
import multiprocessing
from numba import jit
from joblib import Parallel, delayed
import yaml

from mc2hessian import (LocalPDF, XGrid, Flavors, invcov_sqrtinvcov,
                        comp_hess, DEFAULT_EPSILON)


DEFAULT_MAXITER = 2000

def minintask(i, A, nf, nx, n, xfxQ, f0, sqrtinvcov):
    b = numpy.zeros(shape=(nf*nx))
    for fi in range(nf):
        for ix in range(nx):
            b[nx*fi + ix] = xfxQ[i, fi, ix]-f0[fi, ix]
    b = sqrtinvcov.dot(b)
    return numpy.linalg.lstsq(A,b)[0]

def main(pdf_name, nrep, Q, epsilon, max_iters=DEFAULT_MAXITER):
    # Get input set name

    print "- GA Basis selector for Monte Carlo 2 Hessian conversion at", Q, "GeV"

    # Loading basic elements
    fl = Flavors()
    xgrid = XGrid()
    pdf = LocalPDF(pdf_name, nrep, xgrid, fl, Q, eps=epsilon)
    index = pdf.fin
    indextmp = numpy.copy(index)
    nx = xgrid.n
    nf = fl.n

    # build covmat
    cov = pdf.pdfcovmat()
    invcov, sqrtinvcov = invcov_sqrtinvcov(cov)

    # start ga
    num_cores = multiprocessing.cpu_count()
    nite = 0
    nitemax = max_iters
    berf = 1e8
    numpy.random.seed(0)

    prior_cv = pdf.f0
    prior_std = pdf.std

    file = pdf_name + "_hessian_" + str(nrep) + ".log"
    resultname =  pdf_name + "_hessian_" + str(nrep) + ".yaml"
    print "\n- Fitting, output redirected to log file", file
    log = open(file, "a")
    sys.stdout = log

    while (nite < nitemax):

        if nite > 0:
            # copy index vector
            indextmp = numpy.copy(index)

            # perform mutations - ga setup
            g = numpy.random.uniform()
            nmut = 4
            if (g <= 0.3): nmut = 1
            elif (g > 0.3 and g <= 0.6): nmut = 2
            elif (g > 0.6 and g <= 0.7): nmut = 3
            for t in range(nmut):
                done = False
                while done == False:
                    val = numpy.random.randint(1, pdf.n_rep+1)
                    if val not in indextmp: done = True
                pos = numpy.random.randint(0, nrep)
                indextmp[pos] = val
            pdf.rebase(indextmp)

        # create matrix to be solved
        A = numpy.zeros(shape=(nf*nx, nrep))
        for fi in range(nf):
            for ix in range(nx):
                ii = nx*fi + ix
                for r in range(nrep):
                    A[ii, r] = pdf.xfxQ[r, fi, ix]-pdf.f0[fi, ix]
        A = sqrtinvcov.dot(A)

        # solve the linear system
        an = numpy.zeros(shape=(pdf.n_rep, nrep))
        an = Parallel(n_jobs=num_cores)(delayed(minintask)(i,A,nf,nx,nrep,pdf.xfxQ,pdf.f0,sqrtinvcov) for i in range(pdf.n_rep))

        # create acov
        acov = numpy.cov(an, rowvar=0)
        ainvcov = numpy.linalg.inv(acov)

        if not numpy.allclose(numpy.dot(acov, ainvcov), numpy.eye(len(acov))):
            print " [Error] Too redundant basis, try to reduce the size of the basis."
            continue

        # Step 4: solve the system
        eigenvalues, vec = numpy.linalg.eigh(ainvcov)
        for i in range(len(vec)): vec[i] /= eigenvalues[i]**0.5

        # Step 5: quick test
        est = 0
        for f in range(fl.n):
            for x in range(xgrid.n):
                if pdf.mask[f, x]:
                    cv = prior_cv[f,x]
                    t0 = prior_std[f,x]
                    t1 = comp_hess(nrep, vec, pdf.xfxQ, f, x, cv)
                    if t0 != 0: est += abs((t1-t0)/t0)

        if est < berf:
            berf = est
            index = numpy.copy(indextmp)

        print "- Iteration:", nite, " ERF:", berf
        print numpy.sort(index)
        nite += 1

    result = {'Iterations': max_iters,
              'Final ERF': float(berf),
              'pdf_name':pdf_name,
              'nrep':nrep,
              'Q':Q ,
              'epsilon':epsilon,
              'basis': numpy.sort(index).tolist()}

    print("Writing results file %s" % resultname)
    with open(resultname, 'w') as f:
        yaml.dump(result, f, default_flow_style=False)
    log.close()

def usage():
    print "usage: ./basisga [PDF LHAPDF set] [Number of replicas] [Input energy]\n"
    exit()

def splash():

    print "   _               _                  "
    print "  | |__   __ _ ___(_)___  __ _  __ _  "
    print "  | '_ \ / _` / __| / __|/ _` |/ _` | "
    print "  | |_) | (_| \__ \ \__ \ (_| | (_| | "
    print "  |_.__/ \__,_|___/_|___/\__, |\__,_| "
    print "                         |___/        "
    print "\n  __v" + __version__ + "__ Author: Stefano Carrazza\n"

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('pdf_name',
                        help = "Name of LHAPDF set")
    parser.add_argument('nrep',
                        help="Number of basis vectors", type=int)
    parser.add_argument('Q', type=float,
                        help="Energy scale.")
    parser.add_argument('--epsilon', type=float, default=DEFAULT_EPSILON,
                        help="Minimum ratio between one sigma and "
                        "68%% intervals to select point.")
    parser.add_argument('--max-iters', type=int, default=DEFAULT_MAXITER)
    args = parser.parse_args()
    splash()
    main(**vars(args))
