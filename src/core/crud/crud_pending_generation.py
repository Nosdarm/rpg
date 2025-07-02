from src.core.crud_base_definitions import CRUDBase
from src.models import PendingGeneration

class CRUDPendingGeneration(CRUDBase[PendingGeneration]):
    pass

pending_generation_crud = CRUDPendingGeneration(PendingGeneration)
