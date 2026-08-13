from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from django.http import JsonResponse
from functools import wraps

def check_auth(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token = request.session.get('auth_token')
        if not token:
            return redirect('pages:login')

        user_data = request.session.get('user_data', {}) or {}
        role = str(user_data.get('role', '')).upper()

        if role == 'CUSTOMER':
            resolver = getattr(request, 'resolver_match', None)
            url_name = resolver.url_name if resolver else None
            customer_allowed_views = {
                'catalog',
                'catalog_by_channel',
                'product_detail',
                'cart_add_item_proxy',
                'cart_items_proxy',
                'cart_update_quantity_proxy',
                'cart_remove_item_proxy',
                'cart_clear_proxy',
                'cart_summary_proxy',
                'catalog_pdf_generate_proxy',
            }

            if url_name and url_name not in customer_allowed_views:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': '403',
                        'statusMsg': 'Access denied for customer role.',
                    }, status=403)
                return redirect('pages:catalog')

        return view_func(request, *args, **kwargs)
    return wrapper

class ComponentsView(TemplateView):
    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return check_auth(view)

# Create your views here.

# base-ui
base_ui_alerts_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-alerts.html")
base_ui_badges_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-badges.html")
base_ui_buttons_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-buttons.html")
base_ui_colors_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-colors.html")
base_ui_cards_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-cards.html")
base_ui_carousel_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-carousel.html")
base_ui_dropdowns_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-dropdowns.html")
base_ui_grid_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-grid.html")
base_ui_images_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-images.html")
base_ui_tabs_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-tabs.html")
base_ui_accordions_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-accordions.html")
base_ui_modals_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-modals.html")
base_ui_offcanvas_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-offcanvas.html")
base_ui_placeholders_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-placeholders.html")
base_ui_progress_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-progress.html")
base_ui_notifications_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-notifications.html")
base_ui_media_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-media.html")
base_ui_embed_video_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-embed-video.html")
base_ui_typography_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-typography.html")
base_ui_lists_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-lists.html")
base_ui_general_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-general.html")
base_ui_utilities_view = ComponentsView.as_view(template_name = "components/bootstrap-ui/ui-utilities.html")

# advance-ui
advance_ui_sweetalerts_view = ComponentsView.as_view(template_name = "components/advance-ui/advance-ui-sweetalerts.html")
advance_ui_nestable_list_view = ComponentsView.as_view(template_name = "components/advance-ui/advance-ui-nestable.html")
advance_ui_scrollbar_view = ComponentsView.as_view(template_name = "components/advance-ui/advance-ui-scrollbar.html")
advance_ui_swiper_view = ComponentsView.as_view(template_name = "components/advance-ui/advance-ui-swiper.html")
advance_ui_ratings_view = ComponentsView.as_view(template_name = "components/advance-ui/advance-ui-ratings.html")
advance_ui_highlight_view = ComponentsView.as_view(template_name = "components/advance-ui/advance-ui-highlight.html")
advance_ui_scrollspy_view = ComponentsView.as_view(template_name = "components/advance-ui/advance-ui-scrollspy.html")

# forms
forms_elements_view = ComponentsView.as_view(template_name = "components/forms/forms-elements.html")
forms_select_view = ComponentsView.as_view(template_name = "components/forms/forms-select.html")
forms_checkboxs_radios_view = ComponentsView.as_view(template_name = "components/forms/forms-checkboxs-radios.html")
forms_pickers_view = ComponentsView.as_view(template_name = "components/forms/forms-pickers.html")
forms_masks_view = ComponentsView.as_view(template_name = "components/forms/forms-masks.html")
forms_advanced_view = ComponentsView.as_view(template_name = "components/forms/forms-advanced.html")
forms_range_sliders_view = ComponentsView.as_view(template_name = "components/forms/forms-range-sliders.html")
forms_validation_view = ComponentsView.as_view(template_name = "components/forms/forms-validation.html")
forms_wizard_view = ComponentsView.as_view(template_name = "components/forms/forms-wizard.html")
forms_editors_view = ComponentsView.as_view(template_name = "components/forms/forms-editors.html")
forms_file_uploads_view = ComponentsView.as_view(template_name = "components/forms/forms-file-uploads.html")
forms_layouts_view = ComponentsView.as_view(template_name = "components/forms/forms-layouts.html")
forms_tom_select_view = ComponentsView.as_view(template_name = "components/forms/forms-tom-select.html")

# tables
tables_basic_view = ComponentsView.as_view(template_name = "components/tables/tables-basic.html")
tables_gridjs_view = ComponentsView.as_view(template_name = "components/tables/tables-gridjs.html")
tables_listjs_view = ComponentsView.as_view(template_name = "components/tables/tables-listjs.html")
tables_datatables_view = ComponentsView.as_view(template_name = "components/tables/tables-datatables.html")

# apexcharts
apexcharts_line_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-line.html")
apexcharts_area_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-area.html")
apexcharts_column_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-column.html")
apexcharts_bar_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-bar.html")
apexcharts_mixed_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-mixed.html")
apexcharts_timeline_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-timeline.html")
apexcharts_candlestick_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-candlestick.html")
apexcharts_boxplot_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-boxplot.html")
apexcharts_bubble_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-bubble.html")
apexcharts_scatter_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-scatter.html")
apexcharts_heatmap_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-heatmap.html")
apexcharts_treemap_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-treemap.html")
apexcharts_pie_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-pie.html")
apexcharts_radialbar_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-radialbar.html")
apexcharts_radar_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-radar.html")
apexcharts_polar_area_view = ComponentsView.as_view(template_name = "components/apexcharts/charts-apex-polar.html")

# icons
icons_remix_view = ComponentsView.as_view(template_name = "components/icons/icons-remix.html")
icons_boxicons_view = ComponentsView.as_view(template_name = "components/icons/icons-boxicons.html")
icons_materialdesign_view = ComponentsView.as_view(template_name = "components/icons/icons-materialdesign.html")
icons_bootstrap_view = ComponentsView.as_view(template_name = "components/icons/icons-bootstrap.html")
icons_lineawesome_view = ComponentsView.as_view(template_name = "components/icons/icons-lineawesome.html")

# maps
maps_google_view = ComponentsView.as_view(template_name = "components/maps/maps-google.html")
maps_vector_view = ComponentsView.as_view(template_name = "components/maps/maps-vector.html")
maps_leaflet_view = ComponentsView.as_view(template_name = "components/maps/maps-leaflet.html")

