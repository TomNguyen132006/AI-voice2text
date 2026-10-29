// Pre-generated examples that ship with the site (frontend/public/examples). They open without the backend.
// The credit line is one constant so it is easy to edit once the license text is confirmed.
export const EXAMPLE_CREDIT = 'Source: MIT OpenCourseWare, Prof. Gilbert Strang'

export const EXAMPLES = [
  {
    id: 'example-strang',
    title: 'A pure quadratic example (10-minute excerpt)',
    json: '/examples/strang.json',
    files: '/examples/strang',
    // Counts of the saved file, shown in the library without loading it.
    sections: 3,
    notes: 27,
    judged: false, // this run had no judge step, so its notes are not source-checked
    credit: EXAMPLE_CREDIT,
  },
]

export const findExample = (id) => EXAMPLES.find((example) => example.id === id)
