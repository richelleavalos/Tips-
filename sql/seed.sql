-- Datos de demostración iniciales. Se cargan únicamente cuando una base nueva no contiene productos.
-- Mantener este archivo sincronizado con las reglas del backend que consumen sus tablas.

INSERT INTO categories(name,slug,sort_order) VALUES
('Decoración','decoracion',1),('Hogar','hogar',2),('Moda','moda',3),('Deportes','deportes',4),('Accesorios','accesorios',5),('Oficina','oficina',6);

INSERT INTO products(category_id,name,slug,description,base_price_cents,stock_status,sort_order) VALUES
((SELECT id FROM categories WHERE slug='accesorios'),'Auriculares inalámbricos Premium','auriculares-premium','Sonido claro, acabado sobrio y estuche compacto para uso diario.',5990,'available',1),
((SELECT id FROM categories WHERE slug='moda'),'Mochila Urbana','mochila-urbana','Mochila funcional con compartimentos interiores y opciones de color.',3490,'available',2),
((SELECT id FROM categories WHERE slug='hogar'),'Botella Térmica','botella-termica','Botella reutilizable de acero con acabado mate y personalización.',1990,'available',3),
((SELECT id FROM categories WHERE slug='deportes'),'Zapatillas Running','zapatillas-running','Calzado ligero para movimiento diario con selección de talla.',8990,'low',4),
((SELECT id FROM categories WHERE slug='hogar'),'Lámpara de Escritorio','lampara-escritorio','Luz cálida y diseño compacto para escritorio o mesa auxiliar.',2490,'available',5),
((SELECT id FROM categories WHERE slug='decoracion'),'Vela Terracota','vela-terracota','Vela artesanal con recipiente reutilizable y aromas seleccionables.',1790,'made_to_order',6),
((SELECT id FROM categories WHERE slug='moda'),'Bolso Yute Tips','bolso-yute-tips','Bolso artesanal de yute con detalles personalizables.',4590,'available',7),
((SELECT id FROM categories WHERE slug='oficina'),'Libreta Boceto','libreta-boceto','Libreta de papel reciclado para ideas, planos y notas.',1490,'available',8);

INSERT INTO product_variants(product_id,sku,option_summary,price_cents,stock_quantity) VALUES
((SELECT id FROM products WHERE slug='auriculares-premium'),'TIPS-AUR-001','Negro',NULL,18),
((SELECT id FROM products WHERE slug='mochila-urbana'),'TIPS-MOC-001','Verde',NULL,12),
((SELECT id FROM products WHERE slug='botella-termica'),'TIPS-BOT-001','500 ml',NULL,24),
((SELECT id FROM products WHERE slug='zapatillas-running'),'TIPS-ZAP-001','Talla 38',NULL,4),
((SELECT id FROM products WHERE slug='lampara-escritorio'),'TIPS-LAM-001','Arena',NULL,9),
((SELECT id FROM products WHERE slug='vela-terracota'),'TIPS-VEL-001','Mediana',NULL,20),
((SELECT id FROM products WHERE slug='bolso-yute-tips'),'TIPS-BOL-001','Natural',NULL,7),
((SELECT id FROM products WHERE slug='libreta-boceto'),'TIPS-LIB-001','A5',NULL,30);

INSERT INTO customizations(name,input_type,is_required) VALUES ('Color','select',0),('Acabado','select',0),('Personalización','select',0);
INSERT INTO customization_values(customization_id,label,price_delta_cents) VALUES
((SELECT id FROM customizations WHERE name='Color'),'Verde',0),((SELECT id FROM customizations WHERE name='Color'),'Naranja',0),((SELECT id FROM customizations WHERE name='Color'),'Marrón',0),
((SELECT id FROM customizations WHERE name='Acabado'),'Estándar',0),((SELECT id FROM customizations WHERE name='Acabado'),'Premium',900),
((SELECT id FROM customizations WHERE name='Personalización'),'Sin personalizar',0),((SELECT id FROM customizations WHERE name='Personalización'),'Iniciales',500),((SELECT id FROM customizations WHERE name='Personalización'),'Diseño especial',1500);
INSERT INTO product_customizations(product_id,customization_id,sort_order)
SELECT p.id,c.id,c.id FROM products p CROSS JOIN customizations c WHERE p.slug IN('mochila-urbana','botella-termica','vela-terracota','bolso-yute-tips');

INSERT INTO portfolio_projects(title,slug,category,summary,description,location,completed_year,is_published,sort_order) VALUES
('Casa Horizonte','casa-horizonte','Remodelación','Vivienda unifamiliar renovada para abrir luz y conexión entre áreas.','Reorganización de áreas sociales, actualización de acabados y una nueva relación entre interior y jardín. El proyecto prioriza recorridos claros, luz natural y materiales de mantenimiento simple.','Valle de Bravo',2023,1,1),
('Oficina Bosque','oficina-bosque','Interiores','Espacio de trabajo cálido con vegetación y materiales honestos.','Diseño interior para un equipo pequeño con estaciones flexibles, sala de reunión y zonas de pausa.','San Salvador',2025,1,2),
('Casa Alero','casa-alero','Eco-friendly','Vivienda compacta con estrategias pasivas y sombra generosa.','Propuesta residencial enfocada en ventilación cruzada, protección solar y uso responsable de materiales.','La Libertad',2024,1,3),
('Torre Laguna','torre-laguna','Interiores','Interior residencial contemporáneo con almacenamiento integrado.','Interiores sobrios donde la carpintería organiza el espacio y reduce el ruido visual.','San Salvador',2024,1,4),
('Casa Patio','casa-patio','Remodelación','Un patio central vuelve a ser el corazón de la vivienda.','Remodelación que recupera iluminación, ventilación y convivencia alrededor de un patio existente.','Santa Tecla',2025,1,5),
('Estudio Creativo','estudio-creativo','Interiores','Taller flexible para creación, reuniones y exhibición.','Un espacio pequeño se convierte en estudio adaptable mediante mobiliario móvil y una paleta natural.','Antiguo Cuscatlán',2026,1,6);

INSERT OR IGNORE INTO site_settings(key,value_json,is_public) VALUES
('theme','{"primary":"#173d2b","accent":"#ef7d22","secondary":"#825334","surface":"#f7f7f2"}',1),
('brand','{"name":"Tips","currency":"USD","country":"SV"}',1);
