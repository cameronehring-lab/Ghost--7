import sympy as sp
import numpy as np
import scipy as sc
from qutip import Qobj, basis, sigmax, sigmay, sigmaz, destroy, create, mesolve, qeye
import qutip as qt
from einsteinpy.symbolic import MetricTensor, ChristoffelSymbols, RiemannCurvatureTensor
import einsteinpy as ep

def test_physics_workbench_logic():
    print("--- Testing SymPy ---")
    x, y = sp.symbols('x y')
    expr = x**2 + 2*x + 1
    factored = sp.factor(expr)
    print(f"Factored x^2 + 2x + 1: {factored}")
    assert str(factored) == "(x + 1)**2"

    print("\n--- Testing QuTiP ---")
    # Simple qubit rotation
    state = basis(2, 0)
    op = sigmax()
    new_state = op * state
    print(f"Qubit state after Sigma-X: {new_state}")
    assert new_state[1, 0] == 1.0

    print("\n--- Testing EinsteinPy ---")
    # Schwarzschild metric symbolic
    t, r, theta, phi = sp.symbols('t r theta phi')
    sch = sp.symbols('r_s')
    metric = [
        [-(1 - sch / r), 0, 0, 0],
        [0, 1 / (1 - sch / r), 0, 0],
        [0, 0, r**2, 0],
        [0, 0, 0, r**2 * sp.sin(theta)**2]
    ]
    m_obj = MetricTensor(metric, (t, r, theta, phi))
    print(f"Metric component g_00: {m_obj.tensor()[0,0]}")
    
    print("\n--- All basic physics checks passed! ---")

if __name__ == "__main__":
    try:
        test_physics_workbench_logic()
    except Exception as e:
        print(f"Verification failed: {e}")
        exit(1)
