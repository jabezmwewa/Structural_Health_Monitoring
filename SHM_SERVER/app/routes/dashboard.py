from flask import Blueprint, render_template

from config import Config
from app.models import Device, StructuralElement

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    """
    Serves the SHM monitoring dashboard. Injects the device, its structural
    elements, and the threshold specs so the page can paint immediately; live
    values are then fetched from the /api/v2 endpoints by static/main.js.
    """
    device = Device.query.order_by(Device.id).first()
    elements = (
        StructuralElement.query.filter_by(device_id=device.id)
        .order_by(StructuralElement.id)
        .all()
        if device else []
    )

    return render_template(
        'dashboard.html',
        device=device.to_dict() if device else None,
        elements=[e.to_dict() for e in elements],
        thresholds=Config.THRESHOLD_SPECS,
    )
