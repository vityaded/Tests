import os

def combine_files_in_directory(directories, output_file):
    with open(output_file, 'w', encoding='utf-8') as outfile:
        for directory in directories:
            for root, dirs, files in os.walk(directory):
                # Ignore subdirectories by checking if we're still in the top-level folder
                if root == directory:
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                                outfile.write(f"\n\n--- Start of {file_path} ---\n\n")
                                outfile.write(infile.read())
                                outfile.write(f"\n\n--- End of {file_path} ---\n\n")
                        except Exception as e:
                            print(f"Error reading {file_path}: {e}")

if __name__ == "__main__":
    directories = ["./", "./static", "./templates"]  # Root, static, and templates directories
    output_file = "combined_files.txt"
    combine_files_in_directory(directories, output_file)
    print(f"All files combined into {output_file}")
