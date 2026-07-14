"""Controlled acquisition errors."""


class AcquisitionError(RuntimeError):
    pass


class AcquisitionConfigurationError(AcquisitionError):
    pass


class DiscoveryError(AcquisitionError):
    pass


class UnsafeTargetError(AcquisitionError):
    pass


class SnapshotError(AcquisitionError):
    pass


class NoEligibleUrlsError(AcquisitionError):
    pass
