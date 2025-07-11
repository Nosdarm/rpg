from backend.core.crud_base_definitions import CRUDBase
from backend.models import PendingGeneration

class CRUDPendingGeneration(CRUDBase[PendingGeneration]):
    pass

pending_generation_crud = CRUDPendingGeneration(PendingGeneration)
