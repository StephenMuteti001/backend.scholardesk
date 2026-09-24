from exam_materials.exam_material import ExamMaterial


VALID_TRANSITIONS = {
    "draft": {
        "in-review",
        "archived",
    },

    "in-review": {
        "draft",
        "published",
        "archived",
    },

    "published": {
        "archived",
    },

    "archived": {
        "draft",
    },
}





MATERIAL_STATUSES = {
    "draft",
    "in-review",
    "published",
    "archived",
}


SORTABLE_FIELDS = {
    "title": ExamMaterial.title,
    "exam": ExamMaterial.exam,
    "subject": ExamMaterial.subject,
    "status": ExamMaterial.status,
    "price": ExamMaterial.price,
    "downloads": ExamMaterial.downloads,
    "revenue": ExamMaterial.revenue,
    "created_at": ExamMaterial.created_at,
    "updated_at": ExamMaterial.updated_at,
}



EDITABLE_FIELDS = {
    "title",
    "description",
    "exam",
    "subject",
    "expert_id",
    "price",
}
