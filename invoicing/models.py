from django.db import models


class UploadedFile(models.Model):
    file = models.FileField(upload_to='uploads/')
    file_type = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)


class MergedData(models.Model):
    material = models.CharField(max_length=100)
    supplier = models.CharField(max_length=100)
    posting_date = models.DateField(verbose_name="posting_date")
    document_date = models.DateField(verbose_name="document_date")
    gpdb_price_current = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="gpdb_price_current")
    invoice_pcs_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="invoice_pcs_price")
    quantity = models.IntegerField()
    difference_value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="difference_value")
    reference = models.CharField(max_length=100)
    mm_doc_number = models.CharField(max_length=100, verbose_name="mm_doc_number")
    comments = models.TextField()
    full_price_per_1000_pcs = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="full_price_per_1000_pcs")
    site_name = models.CharField(max_length=100, default='', verbose_name="site_name")
    affiliate = models.CharField(max_length=100)
    mpf_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="mpf_price")
    mpf_price_valid_from = models.DateField(verbose_name="mpf_price_valid_from")
    mpf_price_valid_to = models.DateField(verbose_name="mpf_price_valid_to")
    base_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="base_price")
    price_base = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="price_base")
    base_price_valid_from = models.DateField(verbose_name="base_price_valid_from")
    base_price_valid_to = models.DateField(verbose_name="base_price_valid_to")
    metal_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="metal_price")
    moq = models.IntegerField()
    released = models.BooleanField(default=False)
    upload_date = models.DateField(auto_now_add=True, verbose_name="upload_date")
    root_cause = models.CharField(max_length=100, verbose_name="root_cause")

    def __str__(self):
        return self.material

