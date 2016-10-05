# Copyright 2014-2016 The ODL development group
#
# This file is part of ODL.
#
# ODL is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ODL is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ODL.  If not, see <http://www.gnu.org/licenses/>.

"""(Quasi-)Newton schemes to find zeros of functions."""

# Imports for common Python 2/3 codebase
from __future__ import print_function, division, absolute_import
from future import standard_library
standard_library.install_aliases()

import numpy as np
from odl.operator import IdentityOperator
from odl.solvers.util import ConstantLineSearch
from odl.solvers.iterative.iterative import conjugate_gradient


__all__ = ('newtons_method', 'bfgs_method', 'broydens_method')


# TODO: update all docs


def _bfgs_multiply(s, y, x, hessinv_estimate=None):
    """Computes ``Hn^-1(x)`` for the L-BFGS method.

    Parameters
    ----------
    s : `sequence` of `LinearSpaceElement`
        The ``s`` coefficients in the BFGS update, see Notes.
    y : `sequence` of `LinearSpaceElement`
        The ``y`` coefficients in the BFGS update, see Notes.
    x : `LinearSpaceElement`
        Point in which to evaluate the product.
    hessinv_estimate : `Operator`, optional
        Initial estimate of the hessian ``H0^-1``.

    Notes
    -----
    :math:`H_n^{-1}` is defined recursively as

    .. math::
        H_{n+1}^{-1} =
        \\left(I - \\frac{ s_n y_n^T}{y_n^T s_n} \\right)
        H_{n}^{-1}
        \\left(I - \\frac{ y_n s_n^T}{y_n^T s_n} \\right) +
        \\frac{s_n s_n^T}{y_n^T \, s_n}

    With :math:`H_0^{-1}` given by ``hess_estimate``.
    """
    assert len(s) == len(y)

    r = x.copy()
    alphas = np.zeros(len(s))
    rhos = np.zeros(len(s))

    for i in reversed(range(len(s))):
        rhos[i] = 1.0 / y[i].inner(s[i])
        alphas[i] = rhos[i] * (s[i].inner(r))
        r.lincomb(1, r, -alphas[i], y[i])

    if hessinv_estimate is not None:
        r = hessinv_estimate(r)

    for i in range(len(s)):
        beta = rhos[i] * (y[i].inner(r))
        r.lincomb(1, r, alphas[i] - beta, s[i])

    return r


def newtons_method(f, x, line_search=1.0, maxiter=1000, tol=1e-16,
                   cg_iter=None, callback=None):
    """Newton's method for minimizing a functional.

    Notes
    -----
    This is a general and optimized implementation of Newton's method
    for solving the problem:

        :math:`\min f(x)`

    for a differentiable function
    :math:`f: \mathcal{X}\\to \mathbb{R}` on a Hilbert space
    :math:`\mathcal{X}`. It does so by finding a zero of the gradient

        :math:`\\nabla f: \mathcal{X} \\to \mathcal{X}`.

    of finding a root of a function.

    The algorithm is well-known and there is a vast literature about it.
    Among others, the method is described in [BV2004]_, Sections 9.5
    and 10.2 (`book available online
    <http://stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf>`_),
    [GNS2009]_,  Section 2.7 for solving nonlinear equations and Section
    11.3 for its use in minimization, and wikipedia on `Newton's_method
    <https://en.wikipedia.org/wiki/Newton's_method>`_.

    The algorithm works by iteratively solving

        :math:`\partial f(x_k)p_k = -f(x_k)`

    and then updating as

        :math:`x_{k+1} = x_k + \\alpha x_k`,

    where :math:`\\alpha` is a suitable step length (see the
    references). In this implementation the system of equations are
    solved using the conjugate gradient method.

    Parameters
    ----------
    f : `Functional`
        Goal functional. Needs to have ``f.gradient`` and
        ``f.gradient.derivative``.
    x : ``op.domain`` element
        Starting point of the iteration
    line_search : float or `LineSearch`, optional
        Strategy to choose the step length. If a float is given, uses it as a
        fixed step length.
    maxiter : int, optional
        Maximum number of iterations.
    tol : float, optional
        Tolerance that should be used for terminating the iteration.
    cg_iter : int, optional
        Number of iterations in the the conjugate gradient solver,
        for computing the search direction.
    callback : `callable`, optional
        Object executing code per iteration, e.g. plotting each iterate
    """
    # TODO: update doc
    grad = f.gradient
    if x not in grad.domain:
        raise TypeError('`x` {!r} is not in the domain of `f` {!r}'
                        ''.format(x, grad.domain))

    if not callable(line_search):
        line_search = ConstantLineSearch(line_search)

    if cg_iter is None:
        # Motivated by that if it is Ax = b, x and b in Rn, it takes at most n
        # iterations to solve with cg
        cg_iter = grad.domain.size

    # TODO: optimize by using lincomb and avoiding to create copies
    for _ in range(maxiter):

        # Initialize the search direction to 0
        search_direction = x.space.zero()

        # Compute hessian (as operator) and gradient in the current point
        hessian = grad.derivative(x)
        deriv_in_point = grad(x)

        # Solving A*x = b for x, in this case f''(x)*p = -f'(x)
        # TODO: Let the user provide/choose method for how to solve this?
        conjugate_gradient(hessian, search_direction,
                           -deriv_in_point, cg_iter)

        # Computing step length
        dir_deriv = search_direction.inner(deriv_in_point)
        if np.abs(dir_deriv) <= tol:
            return

        step_length = line_search(x, search_direction, dir_deriv)

        # Updating
        x += step_length * search_direction

        if callback is not None:
            callback(x)


def bfgs_method(f, x, line_search=1.0, maxiter=1000, tol=1e-16, maxcor=None,
                hessinv_estimate=None, callback=None):
    """Quasi-Newton BFGS method to minimize a differentiable function.

    Can use either the regular BFGS method, or the limited memory BFGS method.

    Notes
    -----
    This is a general and optimized implementation of a quasi-Newton
    method with BFGS update for solving a general unconstrained
    optimization problem

        :math:`\min f(x)`

    for a differentiable function
    :math:`f: \mathcal{X}\\to \mathbb{R}` on a Hilbert space
    :math:`\mathcal{X}`. It does so by finding a zero of the gradient

        :math:`\\nabla f: \mathcal{X} \\to \mathcal{X}`.

    The QN method is an approximate Newton method, where the Hessian
    is approximated and gradually updated in each step. This
    implementation uses the rank-one BFGS update schema where the
    inverse of the Hessian is recalculated in each iteration.

    The algorithm is described in [GNS2009]_, Section 12.3 and in the
    `BFGS Wikipedia article
    <https://en.wikipedia.org/wiki/Broyden%E2%80%93Fletcher%E2%80%93\
Goldfarb%E2%80%93Shanno_algorithm>`_

    Parameters
    ----------
    f : `Functional`
        Functional with ``f.gradient``
    x : ``f.domain`` element
        Starting point of the iteration
    line_search : float or `LineSearch`, optional
        Strategy to choose the step length. If a float is given, uses it as a
        fixed step length.
    maxiter : int, optional
        Maximum number of iterations.
        ``tol``.
    tol : float, optional
        Tolerance that should be used for terminating the iteration.
    maxcor : int, optional
        Maximum number of correction factors to store. If ``None``, the method
        is the regular BFGS method. If an integer, the method becomes the
        Limited Memory BFGS method.
    hessinv_estimate : `Operator`, optional
        Initial estimate of the inverse of the Hessian operator. Needs to be an
        operator from ``f.domain`` to ``f.domain``.
        Default: Identity on ``f.domain``
    callback : `callable`, optional
        Object executing code per iteration, e.g. plotting each iterate.
    """
    grad = f.gradient
    if x not in grad.domain:
        raise TypeError('`x` {!r} is not in the domain of `grad` {!r}'
                        ''.format(x, grad.domain))

    if not callable(line_search):
        line_search = ConstantLineSearch(line_search)

    ys = []
    ss = []

    grad_x = grad(x)
    for _ in range(maxiter):
        # Determine a stepsize using line search
        search_dir = -_bfgs_multiply(ys, ss, grad_x, hessinv_estimate)
        dir_deriv = search_dir.inner(grad_x)
        if np.abs(dir_deriv) < tol:
            return  # we found an optimum
        step = line_search(x, direction=search_dir, dir_derivative=dir_deriv)

        # Update x
        x_update = search_dir
        x_update *= step
        x += x_update

        grad_x, grad_diff = grad(x), grad_x
        # grad_diff = grad(x) - grad(x_old)
        grad_diff.lincomb(-1, grad_diff, 1, grad_x)

        y_inner_s = grad_diff.inner(x_update)
        if np.abs(y_inner_s) < tol:
            return

        # Update Hessian
        ss += [grad_diff]
        ys += [x_update]
        if maxcor is not None:
            # Throw away factors if they are too many.
            ss = ss[-maxcor:]
            ys = ys[-maxcor:]

        if callback is not None:
            callback(x)


def broydens_method(f, x, line_search=1.0, impl='first', maxiter=1000,
                    tol=1e-16, callback=None):
    """Broyden's first method, a quasi-Newton scheme.

    Notes
    -----
    This is a general and optimized implementation of Broyden's  method,
    a quasi-Newton method for solving a general unconstrained optimization
    problem

        :math:`\min f(x)`

    for a differentiable function
    :math:`f: \mathcal{X}\\to \mathbb{R}` on a Hilbert space
    :math:`\mathcal{X}`. It does so by finding a zero of the gradient

        :math:`\\nabla f: \mathcal{X} \\to \mathcal{X}`

    using a Newton-type update scheme with approximate Hessian.

    The algorithm is described in [Bro1965]_ and [Kva1991]_, and in a
    `Wikipedia article
    <https://en.wikipedia.org/wiki/Broyden's_method>`_.

    Parameters
    ----------
    f : `Functional`
        Functional with ``f.gradient``
    x : ``f.domain`` element
        Starting point of the iteration
    line_search : float or `LineSearch`, optional
        Strategy to choose the step length. If a float is given, uses it as a
        fixed step length.
    impl : {'first', 'second'}
        What version of Broydens method to use. First is also known as Broydens
        'good' method, while the second is known as Broydens 'bad' method.
    maxiter : int, optional
        Maximum number of iterations.
        ``tol``.
    tol : float, optional
        Tolerance that should be used for terminating the iteration.
    callback : `callable`, optional
        Object executing code per iteration, e.g. plotting each iterate.
    """
    grad = f.gradient
    if x not in grad.domain:
        raise TypeError('`x` {!r} is not in the domain of `grad` {!r}'
                        ''.format(x, grad.domain))

    if not callable(line_search):
        line_search = ConstantLineSearch(line_search)

    hess = ident = IdentityOperator(grad.domain)
    grad_x = grad(x)

    for _ in range(maxiter):
        # find step size
        search_dir = -hess(grad_x)
        dir_deriv = search_dir.inner(grad_x)
        if np.abs(dir_deriv) < tol:
            return  # we found an optimum
        step = line_search(x, search_dir, dir_deriv)

        # update x
        delta_x = step * search_dir
        x += delta_x

        # compute new gradient
        grad_x, grad_x_old = grad(x), grad_x
        delta_grad = grad_x - grad_x_old

        # update hessian
        v = hess(delta_grad)
        if impl == 'first':
            divisor = delta_x.inner(v)
            if np.abs(divisor) < tol:
                return
            u = (search_dir - v) * (1 / divisor)
            hess = (ident + u * delta_x.T) * hess
        elif impl == 'second':
            divisor = delta_grad.inner(delta_grad)
            if np.abs(divisor) < tol:
                return
            u = (search_dir - v) * (1 / divisor)
            hess = hess + u * delta_grad.T

        if callback is not None:
            callback(x)


if __name__ == '__main__':
    # pylint: disable=wrong-import-position
    from odl.util.testutils import run_doctests
    run_doctests()