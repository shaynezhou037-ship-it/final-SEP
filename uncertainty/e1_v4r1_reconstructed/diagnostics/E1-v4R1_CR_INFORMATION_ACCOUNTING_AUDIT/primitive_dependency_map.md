# Primitive dependency map

The current zR pair list is `(0,1)` through `(0,8)`. In residual-coordinate noise units, define independent primitives `e_0,...,e_8`, each with covariance `S_relative/2`, where `S_relative=diag(0.00146^2 x3, 0.01780235837^2 x3)`. Each zR row block is `r_(0,j)=e_j-e_0`. Therefore every zR marginal remains exactly `S_relative`, while distinct zR blocks have covariance `S_relative/2` from their shared reference primitive.

The implemented zG equations and `assemble()` allocate an independent six-row relative-noise block per zG pose. They do not name or map a primitive shared with zR; hence this audit assigns zR-zG covariance zero rather than inventing a correlation. zV and zL are likewise independent diagonal blocks in the current model.

`A` has shape (48, 54): 48 zR residual coordinates by 54 primitive coordinates. `Sigma_z_dep=A Sigma_e A^T` is inserted only in the existing zR rows; all frozen marginal row variances are preserved.
