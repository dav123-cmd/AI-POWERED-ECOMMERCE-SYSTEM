from django import template

register = template.Library()

def split_nested(value, arg):
    # Split the arg into two delimiters: e.g., "|," -> row_sep="|", col_sep=","
    # If the user only passes one delimiter (like in your latest snippet), handle that too
    if ',' in arg:
        row_sep, col_sep = arg.split(',')
    else:
        row_sep, col_sep = arg, ',' # Default to comma if only one provided
        
    return [row.split(col_sep) for row in value.split(row_sep)]

# Explicitly register the filter
register.filter('split_nested', split_nested)