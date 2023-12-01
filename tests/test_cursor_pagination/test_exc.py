from contextlib import nullcontext as does_not_raise

import pytest

from paginate_any.exc import check_module_version


_runtime_err = pytest.raises(
    RuntimeError,
    match='Module supports test_module>=2.0.3,<3.0',
)
_value_err = pytest.raises(ValueError, match='Invalid version fmt,\nsee also')


@pytest.mark.parametrize(
    ('v', 'expectation'),
    [
        ('', _value_err),
        ('1.3.0', _runtime_err),
        ('1.4.20', _runtime_err),
        ('2.0.3', does_not_raise()),
        ('2.0.5b10', does_not_raise()),
        ('2.0.post10.dev5', _runtime_err),
        ('2.10.11', does_not_raise()),
        ('3.0.0', _runtime_err),
        ('not_valid', _value_err),
    ],
)
def test_required_version(v: str, expectation):
    with expectation:
        check_module_version('test_module', v, (2, 0, 3), (3, 0))


def test_inf_max_version():
    check_module_version('test_module', '500.0', (2, 0))
    with pytest.raises(RuntimeError, match='Module supports test_module>=2.0'):
        check_module_version('test_module', '1.0', (2, 0))
