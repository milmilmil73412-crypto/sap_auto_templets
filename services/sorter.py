from models.schema import VendorBid


def sort_vendors(vendors: list) -> list:
    """Filter excluded vendors, sort ascending by price, assign ranks."""
    active = [v for v in vendors if not v.is_excluded and v.unit_price > 0]
    active.sort(key=lambda v: v.unit_price)

    rank = 1
    for i, v in enumerate(active):
        if i > 0 and active[i].unit_price == active[i - 1].unit_price:
            v.rank = active[i - 1].rank  # 동순위
        else:
            v.rank = rank
        rank += 1

    return active
