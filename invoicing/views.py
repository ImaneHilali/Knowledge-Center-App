from django.shortcuts import render, redirect
from .forms import UploadFileForm, DynamicFilterForm
from django.http import HttpResponse
from .models import UploadedFile, MergedData
import pandas as pd
from django.http import JsonResponse
import json
from django.template.loader import render_to_string
from collections import Counter


def upload_files(request):
    if request.method == 'POST':
        sap_form = UploadFileForm(request.POST, request.FILES, prefix='sap')
        gpdb_form = UploadFileForm(request.POST, request.FILES, prefix='gpdb')
        supplier_form = UploadFileForm(request.POST, request.FILES, prefix='supplier')

        # Process SAP file if uploaded
        if 'sap-file' in request.FILES and sap_form.is_valid():
            sap_file = sap_form.save(commit=False)
            sap_file.file_type = 'SAP'
            sap_file.save()

        # Process GPDB file if uploaded
        if 'gpdb-file' in request.FILES and gpdb_form.is_valid():
            gpdb_file = gpdb_form.save(commit=False)
            gpdb_file.file_type = 'GPDB'
            gpdb_file.save()

        # Process Supplier file if uploaded
        if 'supplier-file' in request.FILES and supplier_form.is_valid():
            supplier_file = supplier_form.save(commit=False)
            supplier_file.file_type = 'Supplier Price List'
            supplier_file.save()

        # Redirect to a success page or back to the form with a success message
        return redirect('upload_success')

    else:
        sap_form = UploadFileForm(prefix='sap')
        gpdb_form = UploadFileForm(prefix='gpdb')
        supplier_form = UploadFileForm(prefix='supplier')

    return render(request, 'upload_files.html', {
        'sap_form': sap_form,
        'gpdb_form': gpdb_form,
        'supplier_form': supplier_form
    })


def upload_success(request):
    # Fetch data from MergedData model
    merged_data = MergedData.objects.all()
    context = {'merged_data': merged_data}
    return render(request, 'upload_success.html', context)


def fill_empty_values_based_on_type(value, field_type):
    if field_type == 'CharField':
        return '' if pd.isnull(value) else value
    elif field_type == 'DateField':
        return pd.Timestamp('1900-01-01') if pd.isnull(value) else pd.to_datetime(value, errors='coerce')
    elif field_type == 'IntegerField':
        return 0 if pd.isnull(value) else value
    elif field_type == 'DecimalField':
        return 0.0 if pd.isnull(value) else value
    elif field_type == 'TextField':
        return '' if pd.isnull(value) else value
    else:
        return value


def read_uploaded_files(file_type):
    files = UploadedFile.objects.filter(file_type=file_type)
    return [pd.read_csv(file.file) for file in files]


def select_and_transform_sap(sap_dfs):
    sap_dfs_selected = []
    for df in sap_dfs:
        df = df.rename(columns={
            'Material': 'material', 'Name': 'supplier', 'Posting Date': 'posting_date', 'Document Date': 'document_date',
            'GPDB Price Current': 'gpdb_price_current', 'Invoice PCS price': 'invoice_pcs_price',
            'Quantity': 'quantity', 'Reference': 'reference', 'Difference Value': 'difference_value',
            'MM Doc. Number': 'mm_doc_number','Comments ':'comments'
        })

        sap_dfs_selected.append(df[['material','supplier','posting_date', 'document_date', 'gpdb_price_current',
                                    'invoice_pcs_price', 'quantity', 'difference_value',
                                    'reference', 'mm_doc_number','comments']])
    return pd.concat(sap_dfs_selected)


def select_and_transform_gpdb(gpdb_dfs):
    gpdb_dfs_selected = []
    for df in gpdb_dfs:
        df = df.rename(columns={
            'ypn': 'material', 'site name': 'site_name', 'mpf price': 'mpf_price',
            'mpf price valid from': 'mpf_price_valid_from', 'mpf price valid to': 'mpf_price_valid_to',
            'base price': 'base_price', 'price base': 'price_base',
            'base price valid from': 'base_price_valid_from',
            'base price valid to': 'base_price_valid_to', 'metal price': 'metal_price'
        })
        df['mpf_price_valid_from'] = pd.to_datetime(df['mpf_price_valid_from'], errors='coerce')
        df['mpf_price_valid_to'] = pd.to_datetime(df['mpf_price_valid_to'], errors='coerce')

        # Remove duplicates and keep the newest date
        df = df.sort_values(by=['mpf_price_valid_to', 'mpf_price_valid_from'], ascending=[False, False])
        df = df.drop_duplicates(subset=['material'], keep='first')
        print("GPDB",df.shape)
        gpdb_dfs_selected.append(df[['material', 'site_name', 'affiliate', 'mpf_price', 'mpf_price_valid_from',
                                     'mpf_price_valid_to', 'base_price', 'price_base',
                                     'base_price_valid_from', 'base_price_valid_to', 'moq', 'metal_price']])
    return pd.concat(gpdb_dfs_selected)


def select_and_transform_supplier(supplier_dfs):
    supplier_dfs_selected = []
    for df in supplier_dfs:
        df = df.rename(columns={
            'Supplier': 'supplier', 'YPN': 'material', 'Full price per 1000 pcs': 'full_price_per_1000_pcs'
        })
        supplier_dfs_selected.append(df[['supplier', 'material', 'full_price_per_1000_pcs']])
    return pd.concat(supplier_dfs_selected)


def merge_sap_gpdb(sap_df, gpdb_df):
    sap_df['document_date'] = pd.to_datetime(sap_df['document_date'], errors='coerce')
    merged_df = pd.merge(sap_df, gpdb_df, on='material', how='left')
    valid_data_final = merged_df[
        (merged_df['document_date'] >= merged_df['mpf_price_valid_from']) &
        (merged_df['document_date'] <= merged_df['mpf_price_valid_to'])
    ]
    invalid_data_final = merged_df[
        ~((merged_df['document_date'] >= merged_df['mpf_price_valid_from']) &
          (merged_df['document_date'] <= merged_df['mpf_price_valid_to']))
    ]
    invalid_data_final['root_cause'] = 'NAP'

    return valid_data_final, invalid_data_final


def final_merge(valid_data_final, invalid_data_final, supplier_df=None):
    # Check if supplier_df exists and is not empty
    if supplier_df is not None and not supplier_df.empty:
        # Mark duplicates in supplier_df
        supplier_df['is_duplicate'] = supplier_df.duplicated(subset='material', keep=False)
        supplier_duplicates_df = supplier_df[supplier_df['is_duplicate']].copy()
        supplier_duplicates_df['root_cause'] = 'Multiple prices in PL'

        # Merge valid_data_final with supplier_df
        final_merge_df = pd.merge(valid_data_final, supplier_df, on='material', how='left', suffixes=('', '_sup'))

        # Check for duplicates in valid_data_final materials within the supplier list
        duplicate_materials = final_merge_df['material'].isin(supplier_duplicates_df['material'])
        final_merge_df.loc[duplicate_materials, 'root_cause'] = 'Multiple prices in PL'

        # Check for missing parts and assign root cause
        #missing_condition = final_merge_df['full_price_per_1000_pcs'].isna()
        #final_merge_df.loc[missing_condition, 'root_cause'] = 'Missing PN in PL'
    else:
        # If supplier_df does not exist or is empty, just use valid_data_final
        final_merge_df = valid_data_final.copy()

    # Append invalid data to final_merge_df
    final_merge_df = pd.concat([final_merge_df, invalid_data_final], ignore_index=True)

    return final_merge_df


def save_to_db(df, model_class):
    model_class.objects.all().delete()
    for _, row in df.iterrows():
        row_data = {field.name: fill_empty_values_based_on_type(row[field.name], field.get_internal_type())
                    for field in model_class._meta.fields if field.name in row.index}
        model_class.objects.create(**row_data)


def merge_data(request):
    try:
        # Read and transform uploaded files
        sap_files = read_uploaded_files('SAP')
        gpdb_files = read_uploaded_files('GPDB')
        supplier_files = read_uploaded_files('Supplier Price List')

        # Transform files and check if they return a valid DataFrame
        sap_df = select_and_transform_sap(sap_files)
        gpdb_df = select_and_transform_gpdb(gpdb_files)
        supplier_df = select_and_transform_supplier(supplier_files)

        # Convert material to string if sap_df is valid
        if sap_df is not None and not sap_df.empty:
            sap_df['material'] = sap_df['material'].astype(str)
        else:
            sap_df = pd.DataFrame()

        # Merge valid and invalid data from SAP and GPDB
        if sap_df.empty or gpdb_df is None or gpdb_df.empty:
            valid_data_final = pd.DataFrame()
            invalid_data_final = pd.DataFrame()
        else:
            valid_data_final, invalid_data_final = merge_sap_gpdb(sap_df, gpdb_df)

        # Perform the final merge with supplier_df
        final_merge_df = final_merge(valid_data_final, invalid_data_final, supplier_df)

        # Save final data to the database
        save_to_db(final_merge_df, MergedData)

        # Treat invoices
        release_invoices(request)

        return redirect('visualize_merged_data')
    except Exception as e:
        # Handle exceptions
        print("Exception during merging and downloading:", e)
        return HttpResponse("An error occurred during merging and downloading: {}".format(str(e)))


def visualize_merged_data(request):
    # Retrieve all merged data
    merged_data = MergedData.objects.all()
    return render(request, 'visualize_merged_data.html', {'merged_data': merged_data})


def export_to_excel(request):
    # Retrieve all merged data
    merged_data = MergedData.objects.all().values()

    # Create a DataFrame
    df = pd.DataFrame(merged_data)

    # Create a response object
    response = HttpResponse(content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="merged_data.xlsx"'

    df.to_excel(response, index=False)

    return response


def release_invoices(request):
    # Query all rows of MergedData
    merged_data = MergedData.objects.all()

    # Initialize counters for released and not released invoices
    released_count = 0
    not_released_count = 0

    # Iterate over each row
    for merged_data_item in merged_data:

        if merged_data_item.material == 'nan':
            merged_data_item.released = False
            merged_data_item.root_cause = 'No Material Number Found'

        else:
            if merged_data_item.gpdb_price_current >= merged_data_item.invoice_pcs_price:
                merged_data_item.released = True
                merged_data_item.root_cause = 'Matching Invoice Price and Current GPDB Price'

            else:
                if not (merged_data_item.mpf_price_valid_from <= merged_data_item.document_date <= merged_data_item.mpf_price_valid_to):
                    merged_data_item.released = False
                    merged_data_item.root_cause = 'No Active Price'
                else:
                    if merged_data_item.affiliate not in ["YEL", "Yazaki"]:
                        merged_data_item.released = False
                        merged_data_item.root_cause = 'Wrong Affiliate in GPDB'
                    else:
                        if merged_data_item.invoice_pcs_price <= merged_data_item.mpf_price:
                            merged_data_item.released = True
                            merged_data_item.root_cause = 'Matching Invoice Price and GPDB-Price at Invoice Date'

                        else:
                            calculation1 = ((merged_data_item.invoice_pcs_price - merged_data_item.mpf_price) / merged_data_item.price_base) * merged_data_item.quantity
                            calculation2 = (merged_data_item.invoice_pcs_price / merged_data_item.price_base) * merged_data_item.quantity
                            calculation2 = calculation1 / calculation2

                            if calculation1 < 40 and calculation2 < 0.05:
                                merged_data_item.released = True
                                merged_data_item.root_cause = 'Price difference within allowed tolerance range'
                            else:
                                if merged_data_item.full_price_per_1000_pcs == 0.0:
                                    merged_data_item.released = False
                                    merged_data_item.root_cause = 'Missing PN in PL'
                                else:
                                    if merged_data_item.root_cause == 'Multiple prices in PL':
                                        merged_data_item.released = False
                                    else:
                                        if merged_data_item.full_price_per_1000_pcs == merged_data_item.mpf_price:
                                            merged_data_item.released = True
                                            merged_data_item.root_cause = 'Matching Price in PL and GPDB-Price at Invoice Date'
                                        else:
                                            if merged_data_item.moq > merged_data_item.quantity:
                                                merged_data_item.released = False
                                                merged_data_item.root_cause = 'The order quantity is lower than MOQ'
                                            else:
                                                if merged_data_item.metal_price != 0.0:
                                                    merged_data_item.released = False
                                                    merged_data_item.root_cause = 'Contact buyer to clarify metal rate with supplier & or request CN'
                                                else:
                                                    merged_data_item.released = False
                                                    merged_data_item.root_cause = 'Contact buyer to clarify with supplier & or request CN'

        # Update released counts
        if merged_data_item.released:
            released_count += 1
        else:
            not_released_count += 1

        # Save the updated instance
        merged_data_item.save()


def release_invoice(request):
    material = request.GET.get('material')

    if material:
        # Query all rows for the specified material
        merged_data = MergedData.objects.filter(material=material)

        # Initialize a list to store the decision tree steps for each row
        decision_steps_list = []

        # Count the number of times the material has been repeated
        material_count = merged_data.count()

        # Initialize counters for released and not released invoices
        released_count = 0
        not_released_count = 0

        # Iterate over each row
        for merged_data_item in merged_data:
            # Initialize a list to store the decision tree steps for the current row
            decision_steps = []

            # Step 1: Compare gpdb_price_current with invoice_pcs_price
            if merged_data_item.gpdb_price_current != 0.0:
                if merged_data_item.gpdb_price_current >= merged_data_item.invoice_pcs_price:
                    merged_data_item.released = True
                    decision_steps.append({
                        'step': f"Step 1: GPDB Price Current ({merged_data_item.gpdb_price_current}) >= Invoice PCS Price ({merged_data_item.invoice_pcs_price}).",
                        'result': 'Released',
                        'root_cause': merged_data_item.root_cause,
                        'released': True
                    })
                else:
                    decision_steps.append({
                        'step': f"Step 1: GPDB Price Current ({merged_data_item.gpdb_price_current}) < Invoice PCS Price ({merged_data_item.invoice_pcs_price}).",
                        'result': 'Continue',
                        'released': None
                    })
            else:
                decision_steps.append({
                    'step': "Step 1: No GPDB Price in SAP.",
                    'result': 'Continue',
                    'released': None
                })

            # Step 2: Check the validity of mpf_price_valid_from and mpf_price_valid_to
            if not (merged_data_item.mpf_price_valid_from <= merged_data_item.document_date <= merged_data_item.mpf_price_valid_to):
                merged_data_item.released = False
                decision_steps.append({
                    'step': f"Step 2: Document Date ({merged_data_item.document_date}) not in MPF Price Valid Range ({merged_data_item.mpf_price_valid_from} , {merged_data_item.mpf_price_valid_to}).",
                    'result': 'Not Released',
                    'root_cause': merged_data_item.root_cause,
                    'released': False
                })
            else:
                decision_steps.append({
                    'step': f"Step 2: Document Date ({merged_data_item.document_date}) in MPF Price Valid Range ({merged_data_item.mpf_price_valid_from} , {merged_data_item.mpf_price_valid_to}).",
                    'result': 'Continue',
                    'released': None
                })

                # Step 3: Check affiliate condition
                if merged_data_item.affiliate not in ["YEL", "Yazaki"]:
                    merged_data_item.released = False
                    decision_steps.append({
                        'step': f"Step 3: Affiliate ({merged_data_item.affiliate}) is wrong, we only use : YEL and Yazaki.",
                        'result': 'Not Released',
                        'root_cause': merged_data_item.root_cause,
                        'released': False
                    })
                else:
                    decision_steps.append({
                        'step': f"Step 3: The Affiliate is correct: {merged_data_item.affiliate}.",
                        'result': 'Continue',
                        'released': None
                    })

                    # Step 4: Compare invoice_pcs_price with mpf_price
                    if merged_data_item.invoice_pcs_price <= merged_data_item.mpf_price:
                        merged_data_item.released = True
                        decision_steps.append({
                            'step': f"Step 4: Invoice PCS Price ({merged_data_item.invoice_pcs_price}) <= MPF Price ({merged_data_item.mpf_price}).",
                            'result': 'Released',
                            'root_cause': merged_data_item.root_cause,
                            'released': True
                        })
                    else:
                        decision_steps.append({
                            'step': f"Step 4: Invoice PCS Price ({merged_data_item.invoice_pcs_price}) > MPF Price ({merged_data_item.mpf_price}).",
                            'result': 'Continue',
                            'released': None
                        })

                        # Step 5: Calculate tolerance range
                        calculation1 = ((merged_data_item.invoice_pcs_price - merged_data_item.mpf_price) / merged_data_item.price_base) * merged_data_item.quantity
                        calculation2 = (merged_data_item.invoice_pcs_price / merged_data_item.price_base) * merged_data_item.quantity
                        calculation2 = calculation1 / calculation2

                        # Format the calculations to two decimal places
                        calculation1_formatted = f"{calculation1:.2f}"
                        calculation2_formatted = f"{calculation2:.2f}"

                        decision_steps.append({
                            'step': f"Step 5: Calculated Tolerance. Calculation 1 = {calculation1_formatted}, Calculation 2 = {calculation2_formatted}",
                            'result': 'Continue',
                            'released': None
                        })

                        # Step 6: Check if calculation1 < 40 and calculation2 < 0.05
                        if calculation1 < 40 and calculation2 < 0.05:
                            merged_data_item.released = True
                            decision_steps.append({
                                'step': "Step 6: Tolerance Check Passed (Calculation 1 < 40 and Calculation 2 < 0.05).",
                                'result': 'Released',
                                'root_cause': merged_data_item.root_cause,
                                'released': True
                            })
                        else:
                            decision_steps.append({
                                'step': "Step 6: Tolerance Check Failed.",
                                'result': 'Continue',
                                'released': None
                            })

                            # Step 7: Check if full_price_per_1000_pcs == 0.0
                            if merged_data_item.full_price_per_1000_pcs == 0.0:
                                merged_data_item.released = False
                                decision_steps.append({
                                    'step': "Step 7: The PN has no PL.",
                                    'result': 'Not Released',
                                    'root_cause': merged_data_item.root_cause,
                                    'released': False
                                })
                            else:
                                decision_steps.append({
                                    'step': "Step 7: PN exist in the PL.",
                                    'result': 'Continue',
                                    'released': None
                                })

                                # Step 8: Check if multiple prices in PL
                                if merged_data_item.root_cause == 'Multiple prices in PL':
                                    merged_data_item.released = False
                                    decision_steps.append({
                                        'step': "Step 8: Multiple prices in PL.",
                                        'result': 'Not Released',
                                        'root_cause': merged_data_item.root_cause,
                                        'released': False
                                    })
                                else:
                                    decision_steps.append({
                                        'step': "Step 8: PN price is unique in PL.",
                                        'result': 'Continue',
                                        'released': None
                                    })

                                    # Step 9: Check if full_price_per_1000_pcs == mpf_price
                                    if merged_data_item.full_price_per_1000_pcs == merged_data_item.mpf_price:
                                        merged_data_item.released = True
                                        decision_steps.append({
                                            'step': f"Step 9: Full Price per 1000 pcs ({merged_data_item.full_price_per_1000_pcs}) matches MPF Price ({merged_data_item.mpf_price}).",
                                            'result': 'Released',
                                            'root_cause': merged_data_item.root_cause,
                                            'released': True
                                        })
                                    else:
                                        decision_steps.append({
                                            'step': f"Step 9: Full Price per 1000 pcs ({merged_data_item.full_price_per_1000_pcs}) does not match MPF Price ({merged_data_item.mpf_price}).",
                                            'result': 'Continue',
                                            'released': None
                                        })

                                        # Step 10: Check if MOQ is higher than quantity
                                        if merged_data_item.moq > merged_data_item.quantity:
                                            merged_data_item.released = False
                                            decision_steps.append({
                                                'step': f"Step 10: MOQ ({merged_data_item.moq}) isn't lower than Quantity ({merged_data_item.quantity}).",
                                                'result': 'Not Released',
                                                'root_cause': merged_data_item.root_cause,
                                                'released': False
                                            })
                                        else:
                                            decision_steps.append({
                                                'step': f"Step 10: MOQ ({merged_data_item.moq}) is lower than Quantity ({merged_data_item.quantity}).",
                                                'result': 'Continue',
                                                'released': None
                                            })

                                            # Step 11: Check if metal_price != 0.0
                                            if merged_data_item.metal_price != 0.0:
                                                merged_data_item.released = False
                                                decision_steps.append({
                                                    'step': f"Step 11: The price Contains Metal Price ({merged_data_item.metal_price})",
                                                    'result': 'Not Released',
                                                    'root_cause': merged_data_item.root_cause,
                                                    'released': False
                                                })
                                            else:
                                                merged_data_item.released = False
                                                decision_steps.append({
                                                    'step': f"Step 11: The price doesn't Contain Metal Price ({merged_data_item.metal_price})",
                                                    'result': 'Not Released',
                                                    'root_cause': merged_data_item.root_cause,
                                                    'released': False
                                                })

            # Update released counts based on final release status
            if merged_data_item.released:
                released_count += 1
            else:
                not_released_count += 1

            # Save the updated instance
            merged_data_item.save()

            # Append the decision tree steps for the current row to the list
            decision_steps_list.append({'material': material, 'decision_steps': decision_steps, 'data': merged_data_item})

        # Render the template with the decision tree steps for each row
        return render(request, 'decision_tree.html', {
            'decision_steps_list': decision_steps_list,
            'material_count': material_count,
            'released_count': released_count,
            'not_released_count': not_released_count
        })
    else:
        return render(request, 'decision_tree.html')


def get_count(request):
    material = request.GET.get('material')
    upload_date = request.GET.get('upload_date')
    supplier = request.GET.get('supplier')
    mm_doc_number = request.GET.get('mm_doc_number')
    reference = request.GET.get('reference')
    root_cause = request.GET.get('root_cause')

    queryset = MergedData.objects.all()

    if material:
        queryset = queryset.filter(material__icontains=material)
    if upload_date:
        queryset = queryset.filter(timestamp__icontains=upload_date)
    if supplier:
        queryset = queryset.filter(supplier__icontains=supplier)
    if mm_doc_number:
        queryset = queryset.filter(mm_doc_number__icontains=mm_doc_number)
    if reference:
        queryset = queryset.filter(reference__icontains=reference)
    if root_cause:
        queryset = queryset.filter(root_cause__icontains=root_cause)

    total_released_count = queryset.filter(released=True).count()
    total_not_released_count = queryset.filter(released=False).count()
    material_count = queryset.count()

    # Data for the bar chart
    root_causes = queryset.values_list('root_cause', flat=True)
    counter = Counter(root_causes)
    labels = list(counter.keys())
    counts = list(counter.values())

    return JsonResponse({
        'material_count': material_count,
        'released_count': total_released_count,
        'not_released_count': total_not_released_count,
        'bar_chart_data': {'labels': labels, 'counts': counts},
    })


def data_analysis(request):
    form = DynamicFilterForm(request.GET)
    queryset = MergedData.objects.all()

    material = None
    material_count = None
    released_count = None
    not_released_count = None
    bar_chart_data = None

    if form.is_valid():
        material = form.cleaned_data.get('material')
        upload_date = form.cleaned_data.get('upload_date')
        supplier = form.cleaned_data.get('supplier')
        mm_doc_number = form.cleaned_data.get('mm_doc_number')
        reference = form.cleaned_data.get('reference')
        root_cause = form.cleaned_data.get('root_cause')

        if material:
            queryset = queryset.filter(material__icontains=material)
        if upload_date:
            queryset = queryset.filter(timestamp__icontains=upload_date)
        if supplier:
            queryset = queryset.filter(supplier__icontains=supplier)
        if mm_doc_number:
            queryset = queryset.filter(mm_doc_number__icontains=mm_doc_number)
        if reference:
            queryset = queryset.filter(reference__icontains=reference)
        if root_cause:
            queryset = queryset.filter(root_cause__icontains=root_cause)

        # Make AJAX request to get the counts
        response = get_count(request)
        counts = json.loads(response.content)

        material_count = counts.get('material_count', None)
        released_count = counts.get('released_count', None)
        not_released_count = counts.get('not_released_count', None)
        bar_chart_data = counts.get('bar_chart_data', None)

    context = {
        'form': form,
        'material': material,
        'material_count': material_count,
        'released_count': released_count,
        'not_released_count': not_released_count,
        'bar_chart_data': json.dumps(bar_chart_data) if bar_chart_data else None,

    }

    return render(request, 'data_analysis.html', context)


def get_table_data(request):
    released = request.GET.get('released', None)
    material = request.GET.get('material', None)
    upload_date = request.GET.get('upload_date', None)
    supplier = request.GET.get('supplier', None)
    mm_doc_number = request.GET.get('mm_doc_number', None)
    reference = request.GET.get('reference', None)
    root_cause = request.GET.get('root_cause', None)

    queryset = MergedData.objects.all()

    if released is not None:
        released = bool(released)
        queryset = queryset.filter(released=released)
    if material:
        queryset = queryset.filter(material__icontains=material)
    if upload_date:
        queryset = queryset.filter(upload_date__icontains=upload_date)
    if supplier:
        queryset = queryset.filter(supplier__icontains=supplier)
    if mm_doc_number:
        queryset = queryset.filter(mm_doc_number__icontains=mm_doc_number)
    if reference:
        queryset = queryset.filter(reference__icontains=reference)
    if root_cause:
        queryset = queryset.filter(root_cause__icontains=root_cause)

    # Render the table HTML using a template
    table_html = render_to_string('table_template.html', {'data': queryset})

    return JsonResponse({'table_html': table_html})


def convert_date_format(date_str):
    # Remove time component if present
    date_part = date_str.split(' ')[0]

    # Split the date into parts
    parts = date_part.split('-')

    if len(parts) == 3:
        # Check if the first part (year) is 4 digits (indicating YYYY-MM-DD format)
        if len(parts[0]) == 4:
            # Format is already YYYY-MM-DD, so return as is
            return date_part
        elif len(parts[2]) == 4:
            # Format is DD-MM-YYYY, so convert to YYYY-MM-DD
            return f'{parts[2]}-{parts[1]}-{parts[0]}'
    return None