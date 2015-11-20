﻿# Copyright 2014, 2015 Jonas Adler
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

"""Default operators defined on any (reasonable) space."""

# Imports for common Python 2/3 codebase
from __future__ import print_function, division, absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import super

import numpy as np
import scipy as sp

# ODL imports
from odl.operator.operator import Operator
from odl.set.pspace import ProductSpace


__all__ = ('ProductSpaceOperator',
           'ComponentProjection', 'ComponentProjectionAdjoint')


class ProductSpaceOperator(Operator):
    """A separable operator on product spaces.

    This is intended for the case where a operator can be decomposed
    as a linear combination of "sub" operators. For example:

    ```
    |A, B, 0| |x|   |Ax + By|
    |0, C, 0| |y| = |  Cy   |
    |0, 0, D| |z|   |  Dz   |
    ```

    """

    def __init__(self, operators, dom=None, ran=None):
        """ Initialize a object

        Parameters
        ----------
        operators : array-like
            An array of operators
        dom : `~odl.ProductSpace`
            Domain, default infers from operators
        ran : `~odl.ProductSpace`
            Range, default infers from operators

        Examples
        --------
        >>> import odl
        >>> r3 = odl.Rn(3)
        >>> X = odl.ProductSpace(r3, r3)
        >>> I = odl.IdentityOperator(r3)

        Sum of elements

        >>> prod_op = ProductSpaceOperator([I, I])

        Diagonal operator, 0 or None means ignore, or the implicit zero op.

        >>> prod_op = ProductSpaceOperator([[I, 0], [None, I]])

        Complicated combinations also possible

        >>> prod_op = ProductSpaceOperator([[I, I], [I, 0]])
        """

        # Validate input data
        if dom is not None and not isinstance(dom, ProductSpace):
            raise TypeError('space {!r} not a ProductSpace instance.'
                            ''.format(dom))
        if ran is not None and not isinstance(ran, ProductSpace):
            raise TypeError('space {!r} not a ProductSpace instance.'
                            ''.format(dom))

        # Convert ops to sparse representation
        self.ops = sp.sparse.coo_matrix(operators)

        if not all(isinstance(op, Operator) for op in self.ops.data):
            raise TypeError('operators {!r} must be a matrix of operators.'
                            ''.format(operators))

        # Set domain and range (or verify if given)
        if dom is None:
            domains = [None] * self.ops.shape[1]

        if ran is None:
            ranges = [None] * self.ops.shape[0]

        for row, col, op in zip(self.ops.row, self.ops.col, self.ops.data):
            if domains[col] is None:
                domains[col] = op.domain
            elif domains[col] != op.domain:
                raise ValueError('Column {}, has inconsistent domains,'
                                 'got {} and {}'
                                 ''.format(col, domains[col], op.domain))

            if ranges[row] is None:
                ranges[row] = op.range
            elif ranges[row] != op.range:
                raise ValueError('Row {}, has inconsistent ranges,'
                                 'got {} and {}'
                                 ''.format(row, ranges[row], op.range))

        if dom is None:
            for col in range(len(domains)):
                if domains[col] is None:
                    raise ValueError('Col {} empty, unable to determine '
                                     'domain, please use `dom` parameter'
                                     ''.format(col, domains[col]))

            dom = ProductSpace(*domains)

        if ran is None:
            for row in range(len(ranges)):
                if ranges[row] is None:
                    raise ValueError('Row {} empty, unable to determine '
                                     'range, please use `ran` parameter'
                                     ''.format(row, ranges[row]))

            ran = ProductSpace(*ranges)

        # Set linearity
        linear = all(op.is_linear for op in self.ops.data)

        super().__init__(domain=dom, range=ran, linear=linear)

    def _apply(self, x, out):
        """ Call the ProductSpace operators inplace

        Parameters
        ----------
        x : domain element
            input vector to be evaluated
        out : range element
            output vector to write result to

        Returns
        -------
        None

        Examples
        --------
        See :meth:`_call`
        """
        has_evaluated_row = np.zeros(self.range.size, dtype=bool)
        for i, j, op in zip(self.ops.row, self.ops.col, self.ops.data):
            if not has_evaluated_row[i]:
                op(x[j], out=out[i])
            else:
                # TODO: optimize
                out[i] += op(x[j])

            has_evaluated_row[i] = True

        for i, evaluated in enumerate(has_evaluated_row):
            if not evaluated:
                out[i].set_zero()

    def _call(self, x):
        """ Call the ProductSpace operators

        Parameters
        ----------
        x : domain element
            input vector to be evaluated

        Returns
        -------
        out : range element
            The result

        Examples
        --------
        >>> import odl
        >>> r3 = odl.Rn(3)
        >>> X = odl.ProductSpace(r3, r3)
        >>> I = odl.IdentityOperator(r3)
        >>> x = X.element([[1, 2, 3], [4, 5, 6]])

        Sum of elements

        >>> prod_op = ProductSpaceOperator([I, I])
        >>> prod_op(x)
        ProductSpace(Rn(3), 1).element([
            [5.0, 7.0, 9.0]
        ])

        Diagonal operator, 0 or None means ignore, or the implicit zero op.

        >>> prod_op = ProductSpaceOperator([[I, 0], [0, I]])
        >>> prod_op(x)
        ProductSpace(Rn(3), 2).element([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0]
        ])

        Complicated combinations

        >>> prod_op = ProductSpaceOperator([[I, I], [I, 0]])
        >>> prod_op(x)
        ProductSpace(Rn(3), 2).element([
            [5.0, 7.0, 9.0],
            [1.0, 2.0, 3.0]
        ])
        """
        out = self.range.zero()
        for i, j, op in zip(self.ops.row, self.ops.col, self.ops.data):
            out[i] += op(x[j])
        return out

    @property
    def adjoint(self):
        """ The adjoint is given by taking the conjugate of the scalar
        """
        # TODO: implement
        raise NotImplementedError()

    def __repr__(self):
        """op.__repr__() <==> repr(op)."""
        return 'ProductSpaceOperator({!r})'.format(self.ops)


class ComponentProjection(Operator):
    """ Projection onto a subspace
    """

    def __init__(self, space, index):
        """ Initialize a Projection

        Parameters
        ----------
        space : `~odl.ProductSpace`
            The space to project from
        index : `int`, `slice`, or `iterable`[int]
            The to project on

        Examples
        --------
        >>> import odl
        >>> r1 = odl.Rn(1)
        >>> r2 = odl.Rn(2)
        >>> r3 = odl.Rn(3)
        >>> X = odl.ProductSpace(r1, r2, r3)

        Projection on n:th component

        >>> proj = odl.ComponentProjection(X, 0)
        >>> proj.range
        Rn(1)

        Projection on sub-space

        >>> proj = odl.ComponentProjection(X, [0, 2])
        >>> proj.range
        ProductSpace(Rn(1), Rn(3))
        """
        self.index = index
        super().__init__(space, space[index], linear=True)

    def _apply(self, x, out):
        """ Extend x onto subspace in place

        See also
        --------
        ComponentProjection._call
        """
        out.assign(x[self.index])

    def _call(self, x):
        """ project x onto subspace

        Parameters
        ----------
        x : domain element
            input vector to be projected

        Returns
        -------
        out : range element
            Projection of x onto subspace

        Examples
        --------
        >>> import odl
        >>> r1 = odl.Rn(1)
        >>> r2 = odl.Rn(2)
        >>> r3 = odl.Rn(3)
        >>> X = odl.ProductSpace(r1, r2, r3)
        >>> x = X.element([[1], [2, 3], [4, 5, 6]])

        Projection on n:th component

        >>> proj = odl.ComponentProjection(X, 0)
        >>> proj(x)
        Rn(1).element([1.0])

        Projection on sub-space

        >>> proj = odl.ComponentProjection(X, [0, 2])
        >>> proj(x)
        ProductSpace(Rn(1), Rn(3)).element([
            [1.0],
            [4.0, 5.0, 6.0]
        ])
        """
        return x[self.index].copy()

    @property
    def adjoint(self):
        """ The adjoint is given by extending along indices, and setting
        zero along the others

        See also
        --------
        ComponentProjectionAdjoint
        """
        return ComponentProjectionAdjoint(self.domain, self.index)


class ComponentProjectionAdjoint(Operator):
    def __init__(self, space, index):
        self.index = index
        super().__init__(space[index], space, linear=True)

    def _apply(self, x, out):
        """ Extend x into the superspace

        See also
        --------
        ComponentProjectionAdjoint._call
        """
        out.set_zero()
        out[self.index] = x

    def _call(self, x):
        """ project x into subspace

        Parameters
        ----------
        x : domain element
            input vector to be projected

        Returns
        -------
        out : range element
            Projection of x into superspace

        Examples
        --------
        >>> import odl
        >>> r1 = odl.Rn(1)
        >>> r2 = odl.Rn(2)
        >>> r3 = odl.Rn(3)
        >>> X = odl.ProductSpace(r1, r2, r3)
        >>> x = X.element([[1], [2, 3], [4, 5, 6]])

        Projection on n:th component

        >>> proj = odl.ComponentProjectionAdjoint(X, 0)
        >>> proj(x[0])
        ProductSpace(Rn(1), Rn(2), Rn(3)).element([
            [1.0],
            [0.0, 0.0],
            [0.0, 0.0, 0.0]
        ])

        Projection on sub-space

        >>> proj = odl.ComponentProjectionAdjoint(X, [0, 2])
        >>> proj(x[0, 2])
        ProductSpace(Rn(1), Rn(2), Rn(3)).element([
            [1.0],
            [0.0, 0.0],
            [4.0, 5.0, 6.0]
        ])
        """
        out = self.range.zero()
        out[self.index] = x
        return out

    @property
    def adjoint(self):
        """ The adjoint is given by the projection onto space[index]

        See also
        --------
        ComponentProjection
        """
        return ComponentProjection(self.range, self.index)


if __name__ == '__main__':
    from doctest import testmod, NORMALIZE_WHITESPACE
    testmod(optionflags=NORMALIZE_WHITESPACE)
