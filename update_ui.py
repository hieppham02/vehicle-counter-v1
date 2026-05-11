import xml.etree.ElementTree as ET

tree = ET.parse('ui/MainForm.ui')
root = tree.getroot()

# Find centralwidget
centralwidget = root.find('.//widget[@name="centralwidget"]')

# 1. Remove left_panel
left_panel = centralwidget.find('.//widget[@name="left_panel"]')
if left_panel is not None:
    centralwidget.remove(left_panel)

# 2. Adjust frame_summary
frame_summary = centralwidget.find('.//widget[@name="frame_summary"]')
if frame_summary is not None:
    geom = frame_summary.find('property[@name="geometry"]/rect')
    geom.find('x').text = '10'
    geom.find('width').text = '1170'

# 3. Adjust frame_video
frame_video = centralwidget.find('.//widget[@name="frame_video"]')
if frame_video is not None:
    geom = frame_video.find('property[@name="geometry"]/rect')
    geom.find('x').text = '10'
    geom.find('width').text = '1170'

# 4. Rename btn_export_f6 to btn_stats and change text
btn_export = centralwidget.find('.//widget[@name="btn_export_f6"]')
if btn_export is not None:
    btn_export.set('name', 'btn_stats')
    btn_export.find('property[@name="text"]/string').text = '📊 Thống Kê'

# 5. Add lbl_chart_radar below btn_stats in layout_controls
layout_controls = centralwidget.find('.//layout[@name="layout_controls"]')
if layout_controls is not None:
    # Insert a new item before the spacer at the end
    new_item = ET.Element('item')
    new_widget = ET.SubElement(new_item, 'widget', {'class': 'QLabel', 'name': 'lbl_chart_radar'})
    # set properties
    prop_ss = ET.SubElement(new_widget, 'property', {'name': 'styleSheet'})
    ET.SubElement(prop_ss, 'string', {'notr': 'true'}).text = 'background:transparent;border:none;'
    prop_text = ET.SubElement(new_widget, 'property', {'name': 'text'})
    ET.SubElement(prop_text, 'string').text = ''
    prop_align = ET.SubElement(new_widget, 'property', {'name': 'alignment'})
    ET.SubElement(prop_align, 'set').text = 'Qt::AlignCenter'
    prop_min_h = ET.SubElement(new_widget, 'property', {'name': 'minimumHeight'})
    ET.SubElement(prop_min_h, 'number').text = '220'
    
    layout_controls.insert(len(layout_controls)-1, new_item)

tree.write('ui/MainForm.ui', encoding='utf-8', xml_declaration=True)
print('Done!')
