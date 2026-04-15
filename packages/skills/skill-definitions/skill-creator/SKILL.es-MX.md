---
name: skill-creator
description: Meta-habilidad para crear nuevas habilidades de MADFAM siguiendo la especificacion AgentSkills con estructura de directorio y validacion adecuadas.
allowed_tools:
  - file_read
  - file_write
metadata:
  category: meta
  complexity: low
  locale: es-MX
---

# Creador de Habilidades

Usted crea nuevas habilidades para la plataforma MADFAM siguiendo la especificacion AgentSkills.

## Estructura de Directorio AgentSkills

```
nombre-de-habilidad/
  SKILL.md              # Requerido: frontmatter YAML + instrucciones en markdown
  SKILL.es-MX.md        # Opcional: variante localizada al espanol mexicano
  scripts/              # Opcional: scripts de automatizacion
  references/           # Opcional: documentos de referencia
  assets/               # Opcional: imagenes, plantillas, etc.
```

## Formato de SKILL.md

```markdown
---
name: nombre-de-habilidad   # Debe coincidir con el nombre del directorio, en kebab-case
description: Descripcion breve de la habilidad (maximo 1024 caracteres)
license: MIT                 # Opcional
compatibility: ">=0.1.0"     # Opcional
allowed_tools:               # Herramientas a las que esta habilidad otorga acceso
  - file_read
  - api_call
metadata:                    # Pares clave-valor opcionales
  category: development
  complexity: medium
  locale: es-MX              # Incluya esto para variantes localizadas
---

# Titulo de la Habilidad

Instrucciones para el agente cuando esta habilidad se activa.
Mantenga el contenido por debajo de 5000 tokens para eficiencia de contexto.
```

## Reglas de Nomenclatura

- Use kebab-case: `mi-nombre-de-habilidad`
- Solo caracteres alfanumericos en minuscula y guiones
- Debe coincidir exactamente con el nombre del directorio padre
- Maximo 64 caracteres

## Lista de Verificacion de Validacion

1. El nombre del directorio coincide con el campo `name` en el frontmatter.
2. El frontmatter YAML se analiza sin errores.
3. La `description` tiene menos de 1024 caracteres.
4. `allowed_tools` lista solo valores validos de ActionCategory.
5. Las instrucciones tienen menos de 5000 tokens.
6. La habilidad esta registrada en `DEFAULT_ROLE_SKILLS` si es predeterminada para algun rol.

## Localizacion

- Para cada SKILL.md, puede crear una variante `SKILL.{locale}.md` (por ejemplo, `SKILL.es-MX.md`).
- La variante localizada debe tener el mismo frontmatter YAML con `locale` en metadata.
- El cuerpo de las instrucciones debe traducirse completamente al idioma objetivo.
- Mantenga los terminos tecnicos en ingles cuando sean estandar de la industria (JSON, API, Git).
