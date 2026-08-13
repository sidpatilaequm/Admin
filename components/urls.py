from django.urls import path
from components.views import (
    # bootstrap-ui
    base_ui_alerts_view,
    base_ui_badges_view,
    base_ui_buttons_view,
    base_ui_colors_view,
    base_ui_cards_view,
    base_ui_carousel_view,
    base_ui_dropdowns_view,
    base_ui_grid_view,
    base_ui_images_view,
    base_ui_tabs_view,
    base_ui_accordions_view,
    base_ui_modals_view,
    base_ui_offcanvas_view,
    base_ui_placeholders_view,
    base_ui_progress_view,
    base_ui_notifications_view,
    base_ui_media_view,
    base_ui_embed_video_view,
    base_ui_typography_view,
    base_ui_lists_view,
    base_ui_general_view,
    base_ui_utilities_view,
    
    # advance-ui
    advance_ui_sweetalerts_view,
    advance_ui_nestable_list_view,
    advance_ui_scrollbar_view,
    advance_ui_swiper_view,
    advance_ui_ratings_view,
    advance_ui_highlight_view,
    advance_ui_scrollspy_view,
    
    # forms
    forms_elements_view,
    forms_select_view,
    forms_checkboxs_radios_view,
    forms_pickers_view,
    forms_masks_view,
    forms_advanced_view,
    forms_range_sliders_view,
    forms_validation_view,
    forms_wizard_view,
    forms_editors_view,
    forms_file_uploads_view,
    forms_layouts_view,
    forms_tom_select_view,
    
    # table
    tables_basic_view,
    tables_gridjs_view,
    tables_listjs_view,
    tables_datatables_view,
    
    # apex-charts
    apexcharts_line_view,
    apexcharts_area_view,
    apexcharts_column_view,
    apexcharts_bar_view,
    apexcharts_mixed_view,
    apexcharts_timeline_view,
    apexcharts_candlestick_view,
    apexcharts_boxplot_view,
    apexcharts_bubble_view,
    apexcharts_scatter_view,
    apexcharts_heatmap_view,
    apexcharts_treemap_view,
    apexcharts_pie_view,
    apexcharts_radialbar_view,
    apexcharts_radar_view,
    apexcharts_polar_area_view,
    
    # icons
    icons_remix_view,
    icons_boxicons_view,
    icons_materialdesign_view,
    icons_bootstrap_view,
    icons_lineawesome_view,

    
    # maps
    maps_google_view,
    maps_vector_view,
    maps_leaflet_view,
)

app_name ='components'

urlpatterns = [
    
    # bootstrap-ui
    path('bootstrap-ui/alerts',view=base_ui_alerts_view,name="bootstrap-ui.alerts"),
    path('bootstrap-ui/badges',view=base_ui_badges_view,name="bootstrap-ui.badges"),
    path('bootstrap-ui/buttons',view=base_ui_buttons_view,name="bootstrap-ui.buttons"),
    path('bootstrap-ui/colors',view=base_ui_colors_view,name="bootstrap-ui.colors"),
    path('bootstrap-ui/cards',view=base_ui_cards_view,name="bootstrap-ui.cards"),
    path('bootstrap-ui/carousel',view=base_ui_carousel_view,name="bootstrap-ui.carousel"),
    path('bootstrap-ui/dropdowns',view=base_ui_dropdowns_view,name="bootstrap-ui.dropdowns"),
    path('bootstrap-ui/grid',view=base_ui_grid_view,name="bootstrap-ui.grid"),
    path('bootstrap-ui/images',view=base_ui_images_view,name="bootstrap-ui.images"),
    path('bootstrap-ui/tabs',view=base_ui_tabs_view,name="bootstrap-ui.tabs"),
    path('bootstrap-ui/accordions',view=base_ui_accordions_view,name="bootstrap-ui.accordions"),
    path('bootstrap-ui/modals',view=base_ui_modals_view,name="bootstrap-ui.modals"),
    path('bootstrap-ui/offcanvas',view=base_ui_offcanvas_view,name="bootstrap-ui.offcanvas"),
    path('bootstrap-ui/placeholders',view=base_ui_placeholders_view,name="bootstrap-ui.placeholders"),
    path('bootstrap-ui/progress',view=base_ui_progress_view,name="bootstrap-ui.progress"),
    path('bootstrap-ui/notifications',view=base_ui_notifications_view,name="bootstrap-ui.notifications"),
    path('bootstrap-ui/media',view=base_ui_media_view,name="bootstrap-ui.media"),
    path('bootstrap-ui/embed-video',view=base_ui_embed_video_view,name="bootstrap-ui.embed-video"),
    path('bootstrap-ui/typography',view=base_ui_typography_view,name="bootstrap-ui.typography"),
    path('bootstrap-ui/lists',view=base_ui_lists_view,name="bootstrap-ui.lists"),
    path('bootstrap-ui/general',view=base_ui_general_view,name="bootstrap-ui.general"),
    path('bootstrap-ui/utilities',view=base_ui_utilities_view,name="bootstrap-ui.utilities"),
    
    # advance-ui
    path('advance-ui/sweetalerts',view=advance_ui_sweetalerts_view,name="advance-ui.sweetalerts"),
    path('advance-ui/nestable-list',view=advance_ui_nestable_list_view,name="advance-ui.nestable_list"),
    path('advance-ui/scrollbar',view=advance_ui_scrollbar_view,name="advance-ui.scrollbar"),
    path('advance-ui/swiper',view=advance_ui_swiper_view,name="advance-ui.swiper"),
    path('advance-ui/ratings',view=advance_ui_ratings_view,name="advance-ui.ratings"),
    path('advance-ui/highlight',view=advance_ui_highlight_view,name="advance-ui.highlight"),
    path('advance-ui/scrollspy',view=advance_ui_scrollspy_view,name="advance-ui.scrollspy"),
  
    # forms
    path('forms/elements',view=forms_elements_view,name="forms.elements"),
    path('forms/select',view=forms_select_view,name="forms.select"),
    path('forms/checkboxs-radios',view=forms_checkboxs_radios_view,name="forms.checkboxs_radios"),
    path('forms/pickers',view=forms_pickers_view,name="forms.pickers"),
    path('forms/masks',view=forms_masks_view,name="forms.masks"),
    path('forms/advanced',view=forms_advanced_view,name="forms.advanced"),
    path('forms/range-sliders',view=forms_range_sliders_view,name="forms.range_sliders"),
    path('forms/validation',view=forms_validation_view,name="forms.validation"),
    path('forms/wizard',view=forms_wizard_view,name="forms.wizard"),
    path('forms/editors',view=forms_editors_view,name="forms.editors"),
    path('forms/file-uploads',view=forms_file_uploads_view,name="forms.file_uploads"),
    path('forms/layouts',view=forms_layouts_view,name="forms.layouts"),
    path('forms/tom_select',view=forms_tom_select_view,name="forms.tom_select"),
    
    # tables
    path('tables/basic',view=tables_basic_view,name="tables.basic"),
    path('tables/gridjs',view=tables_gridjs_view,name="tables.gridjs"),
    path('tables/listjs',view=tables_listjs_view,name="tables.listjs"),
    path('tables/datatables',view=tables_datatables_view,name="tables.datatables"),
     
    #  apexcharts
    path('apexcharts/line',view=apexcharts_line_view,name="apexcharts.line"),
    path('apexcharts/area',view=apexcharts_area_view,name="apexcharts.area"),
    path('apexcharts/column',view=apexcharts_column_view,name="apexcharts.column"),
    path('apexcharts/bar',view=apexcharts_bar_view,name="apexcharts.bar"),
    path('apexcharts/mixed',view=apexcharts_mixed_view,name="apexcharts.mixed"),
    path('apexcharts/timeline',view=apexcharts_timeline_view,name="apexcharts.timeline"),
    path('apexcharts/candlestick',view=apexcharts_candlestick_view,name="apexcharts.candlestick"),
    path('apexcharts/boxplot',view=apexcharts_boxplot_view,name="apexcharts.boxplot"),
    path('apexcharts/bubble',view=apexcharts_bubble_view,name="apexcharts.bubble"),
    path('apexcharts/scatter',view=apexcharts_scatter_view,name="apexcharts.scatter"),
    path('apexcharts/heatmap',view=apexcharts_heatmap_view,name="apexcharts.heatmap"),
    path('apexcharts/treemap',view=apexcharts_treemap_view,name="apexcharts.treemap"),
    path('apexcharts/pie',view=apexcharts_pie_view,name="apexcharts.pie"),
    path('apexcharts/radialbar',view=apexcharts_radialbar_view,name="apexcharts.radialbar"),
    path('apexcharts/radar',view=apexcharts_radar_view,name="apexcharts.radar"),
    path('apexcharts/polararea',view=apexcharts_polar_area_view,name="apexcharts.polararea"),
    
    # icons
    path('icons/remix',view=icons_remix_view,name="icons.remix"),
    path('icons/boxicons',view=icons_boxicons_view,name="icons.boxicons"),
    path('icons/materialdesign',view=icons_materialdesign_view,name="icons.materialdesign"),
    path('icons/bootstrap',view=icons_bootstrap_view,name="icons.bootstrap"),
    path('icons/lineawesome',view=icons_lineawesome_view,name="icons.lineawesome"),
    
    # maps
    path('maps/google',view=maps_google_view,name="maps.google"),
    path('maps/vector',view=maps_vector_view,name="maps.vector"),
    path('maps/leaflet',view=maps_leaflet_view,name="maps.leaflet"),
    
]